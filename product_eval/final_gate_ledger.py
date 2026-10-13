"""Durable, conservative paid-attempt accounting for the final operational gate."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class GateStopped(RuntimeError):
    """No request may be sent under the current frozen gate state."""


_RESUMABLE_STOPS = {"authentication", "rate_limit", "repeated_transport_failure"}


def _record_stop(db, reason: str) -> None:
    existing = db.execute("SELECT value FROM settings WHERE key='stop_reason'").fetchone()[0]
    # A late concurrent response cannot turn an integrity/budget stop into one
    # an operator may acknowledge and resume. Preserve the first critical stop.
    if not existing or existing in _RESUMABLE_STOPS and reason not in _RESUMABLE_STOPS:
        db.execute("UPDATE settings SET value=? WHERE key='stop_reason'", (reason,))


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, sources: list[dict], protocol_sha256: str, max_calls: int) -> None:
        # Creation happens before any worker exists. Refuse to replace a ledger.
        with self.path.open("xb"):
            pass
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE controls (event_id INTEGER PRIMARY KEY, event TEXT NOT NULL, reason TEXT NOT NULL, updated REAL NOT NULL);
                CREATE TABLE sources (
                    doc_id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL,
                    state TEXT NOT NULL DEFAULT 'unstarted', receipt_sha256 TEXT,
                    reason TEXT, updated REAL NOT NULL);
                CREATE TABLE attempts (
                    attempt_id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, state TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, reply_sha256 TEXT,
                    prompt_tokens INTEGER, completion_tokens INTEGER,
                    latency_ms REAL, finish_reason TEXT, refusal INTEGER, error_category TEXT,
                    sdk_attempts INTEGER, updated REAL NOT NULL,
                    UNIQUE(doc_id, ordinal));
            """)
            db.executemany("INSERT INTO settings VALUES (?, ?)", [
                ("protocol_sha256", protocol_sha256), ("max_calls", str(max_calls)),
                ("stop_reason", ""), ("consecutive_transport_failures", "0"),
            ])
            db.executemany("INSERT INTO sources(doc_id, ordinal, updated) VALUES (?, ?, ?)",
                           [(row["doc_id"], index, time.time()) for index, row in enumerate(sources)])

    def snapshot(self) -> dict:
        with self.transaction() as db:
            return {
                "settings": dict(db.execute("SELECT key, value FROM settings")),
                "sources": [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY ordinal")],
                "attempts": [dict(row) for row in db.execute("SELECT * FROM attempts ORDER BY attempt_id")],
                "controls": [dict(row) for row in db.execute("SELECT * FROM controls ORDER BY event_id")],
            }

    def claim(self, doc_id: str) -> bool:
        with self.transaction() as db:
            if db.execute("SELECT value FROM settings WHERE key='stop_reason'").fetchone()[0]:
                return False
            return db.execute("UPDATE sources SET state='started', updated=? WHERE doc_id=? AND state='unstarted'",
                              (time.time(), doc_id)).rowcount == 1

    def begin_attempt(self, doc_id: str, request_sha256: str) -> tuple[int, int]:
        """Commit request_begun before returning control to the provider wrapper."""
        failure = None
        result = None
        with self.transaction() as db:
            settings = dict(db.execute("SELECT key, value FROM settings"))
            state = db.execute("SELECT state FROM sources WHERE doc_id=?", (doc_id,)).fetchone()
            count = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            per_source = db.execute("SELECT COUNT(*) FROM attempts WHERE doc_id=?", (doc_id,)).fetchone()[0]
            if settings["stop_reason"]:
                failure = settings["stop_reason"]
            elif state is None or state[0] != "started":
                failure = "source_not_started"
            elif count >= int(settings["max_calls"]):
                failure = "global_call_budget_exhausted"
            elif per_source >= 4:
                failure = "source_call_budget_exhausted"
            if failure:
                db.execute("UPDATE settings SET value=? WHERE key='stop_reason'", (failure,))
            else:
                cursor = db.execute(
                    "INSERT INTO attempts(doc_id, ordinal, state, request_sha256, updated) VALUES (?, ?, 'request_begun', ?, ?)",
                    (doc_id, per_source + 1, request_sha256, time.time()),
                )
                result = (cursor.lastrowid, per_source + 1)
        if failure:
            raise GateStopped(failure)
        assert result is not None
        return result

    def finish_attempt(self, attempt_id: int, reply_sha256: str, reply: dict) -> None:
        category = reply.get("error_category")
        uncertain = reply.get("sdk_attempts") != 1 or bool(reply.get("error") and not category) or bool(category and (category.startswith("transport_") or category in {
            "provider_server", "provider_other", "provider_unknown", "unknown",
        }))
        with self.transaction() as db:
            row = db.execute("SELECT state FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row[0] != "request_begun":
                raise ValueError("Attempt was not pending")
            db.execute("""UPDATE attempts SET state=?, reply_sha256=?, prompt_tokens=?, completion_tokens=?,
                          latency_ms=?, finish_reason=?, refusal=?, error_category=?, sdk_attempts=?, updated=? WHERE attempt_id=?""",
                       ("uncertain" if uncertain else "replied", reply_sha256, reply.get("prompt_tokens"),
                        reply.get("completion_tokens"), reply.get("latency_ms"), reply.get("finish_reason"), bool(reply.get("refusal")),
                        category, reply.get("sdk_attempts"), time.time(), attempt_id))
            failures = int(db.execute("SELECT value FROM settings WHERE key='consecutive_transport_failures'").fetchone()[0])
            failures = failures + 1 if uncertain else 0
            db.execute("UPDATE settings SET value=? WHERE key='consecutive_transport_failures'", (str(failures),))
            stop = ("sdk_retry_contract_violation" if reply.get("sdk_attempts") != 1 else
                    "authentication" if category == "authentication" or reply.get("error") == "http_403" else
                    "rate_limit" if category == "rate_limit" else
                    "request_rejected" if category == "request_rejected" else
                    "repeated_transport_failure" if failures >= 2 else None)
            if stop:
                _record_stop(db, stop)

    def seal_source(self, doc_id: str, receipt_sha256: str, reason: str | None = None) -> None:
        with self.transaction() as db:
            uncertain = db.execute("SELECT 1 FROM attempts WHERE doc_id=? AND state != 'replied' LIMIT 1", (doc_id,)).fetchone()
            state = "uncertain" if uncertain else "sealed"
            updated = db.execute("UPDATE sources SET state=?, receipt_sha256=?, reason=?, updated=? WHERE doc_id=? AND state='started'",
                                 (state, receipt_sha256, reason, time.time(), doc_id)).rowcount
            if updated != 1:
                raise ValueError("Source was not started")

    def recover_interrupted(self) -> int:
        """Never make a started source eligible for another paid attempt."""
        with self.transaction() as db:
            db.execute("UPDATE attempts SET state='uncertain', updated=? WHERE state='request_begun'", (time.time(),))
            return db.execute("UPDATE sources SET state='uncertain', reason='interrupted', updated=? WHERE state='started'",
                              (time.time(),)).rowcount

    def stop(self, reason: str) -> None:
        with self.transaction() as db:
            _record_stop(db, reason)

    def acknowledge_stop(self, expected: str) -> None:
        """Explicitly resume untouched sources without resetting paid attempts."""
        with self.transaction() as db:
            actual = db.execute("SELECT value FROM settings WHERE key='stop_reason'").fetchone()[0]
            if not actual or expected != actual or actual not in _RESUMABLE_STOPS:
                raise GateStopped("stop_acknowledgement_mismatch_or_nonresumable")
            db.execute("INSERT INTO controls(event, reason, updated) VALUES ('operator_resume', ?, ?)", (actual, time.time()))
            db.execute("UPDATE settings SET value='' WHERE key='stop_reason'")
            db.execute("UPDATE settings SET value='0' WHERE key='consecutive_transport_failures'")


@contextmanager
def exclusive_run_lock(path: Path):
    """An OS lock releases on process death; a stale file does not block resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        import os
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise GateStopped("gate_already_running") from None
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise GateStopped("gate_already_running") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
