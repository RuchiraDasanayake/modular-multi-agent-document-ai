"""Private single-host product extraction worker over a Unix socket.

The frontend owns authentication and stages files in the shared data volume.
Only the frontend and this worker mount that volume in Docker Compose.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socketserver
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from idpo.core.storage import data_root
from idpo.product_auto import process_auto
from idpo.product_auto.approved_recipe import ApprovedRecipe, load_approved_recipe
from idpo.product_auto.provider import OpenAICompatibleChat

LOGGER = logging.getLogger(__name__)
RUN_ID = re.compile(r"auto_[a-f0-9]{32}\Z")
MAX_REQUEST_BYTES = 4096
_run_slot = threading.BoundedSemaphore(value=1)


def validate_request(payload: object, *, root: Path | None = None) -> tuple[Path, str, str | None, str | None, ApprovedRecipe | None]:
    """Allow only a staged frontend run, never an arbitrary host path."""
    if not isinstance(payload, dict):
        raise TypeError("Invalid worker request")
    run_id = payload.get("run_id")
    input_dir = payload.get("input_dir")
    model = payload.get("model")
    base_url = payload.get("api_base_url")
    recipe_file = payload.get("approved_recipe_file")
    recipe_digest = payload.get("approved_recipe_sha256")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run id")
    if not isinstance(input_dir, str) or not input_dir:
        raise ValueError("Invalid input directory")
    if bool(model) != bool(base_url):
        raise ValueError("Model and endpoint must be supplied together")
    if model is not None and (not isinstance(model, str) or len(model) > 200):
        raise ValueError("Invalid model")
    if base_url is not None and (not isinstance(base_url, str) or len(base_url) > 2048):
        raise ValueError("Invalid model endpoint")
    if bool(recipe_file) != bool(recipe_digest) or (recipe_file and not model):
        raise ValueError("Approved recipe requires a snapshot, digest, and value model")

    staging_root = ((root or data_root()) / "frontend" / "auto_inputs").resolve()
    staged = Path(input_dir).resolve(strict=True)
    if not staged.is_dir() or staged.parent != staging_root or staged.name != run_id:
        raise ValueError("Input directory is outside this run's staging area")
    if not any(staged.iterdir()):
        raise ValueError("Input directory is empty")
    if any(not child.is_file() or child.is_symlink() for child in staged.iterdir()):
        raise ValueError("Input directory contains an invalid entry")
    if ((root or data_root()) / "product_runs" / run_id).exists():
        raise ValueError("Run id already exists")
    recipe = None
    if recipe_file:
        if not isinstance(recipe_file, str) or not isinstance(recipe_digest, str):
            raise ValueError("Invalid approved recipe reference")
        expected_path = staging_root / f"{run_id}.recipe.json"
        if Path(recipe_file) != expected_path or expected_path.is_symlink():
            raise ValueError("Approved recipe is outside this run's staging area")
        recipe = load_approved_recipe(expected_path, recipe_digest)
    return staged, run_id, model, base_url, recipe


class WorkerHandler(BaseHTTPRequestHandler):
    server_version = "DocAIProductWorker/1"

    def log_message(self, format: str, *args: object) -> None:
        # Never log request bodies, model endpoints, document text, or credentials.
        LOGGER.info("worker request: %s", format % args)

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        if self.path != "/health":
            self._respond(404, {"error": "Not found"})
            return
        self._respond(200, {"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/process-auto":
            self._respond(404, {"error": "Not found"})
            return
        try:
            self.connection.settimeout(10)
            length = int(self.headers.get("Content-Length", ""))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            staged, run_id, model_name, base_url, recipe = validate_request(payload)
        except (ValueError, TypeError, OSError, json.JSONDecodeError):
            self._respond(400, {"error": "Invalid worker request"})
            return
        finally:
            self.connection.settimeout(None)
        if not _run_slot.acquire(blocking=False):
            self._respond(429, {"error": "Worker is busy; retry this run later"})
            return
        try:
            model = (
                OpenAICompatibleChat(base_url=base_url, model=model_name, api_key_env="ICORE_API_KEY")
                if model_name and base_url else None
            )
            process_auto(staged, run_id=run_id, model=model, approved_recipe=recipe)
            self._respond(200, {"run_id": run_id})
        except Exception as exc:  # noqa: BLE001 - do not expose provider or document content
            LOGGER.error("product run %s failed: %s", run_id, type(exc).__name__)
            self._respond(500, {"error": "Extraction failed; check worker logs"})
        finally:
            _run_slot.release()


class ThreadedUnixServer(socketserver.ThreadingMixIn, getattr(socketserver, "UnixStreamServer", socketserver.TCPServer)):
    daemon_threads = True


def main() -> None:
    if not hasattr(socketserver, "UnixStreamServer"):
        raise SystemExit("Product worker requires Unix domain sockets")
    logging.basicConfig(level=logging.INFO)
    socket_path = Path(os.environ.get("PRODUCT_WORKER_SOCKET", "/idpo-data/product-worker.sock"))
    if socket_path.parent.resolve() != data_root().resolve():
        raise SystemExit("Worker socket must be in IDPO_DATA_DIR")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    try:
        with ThreadedUnixServer(str(socket_path), WorkerHandler) as server:
            socket_path.chmod(0o600)
            server.serve_forever(poll_interval=0.5)
    finally:
        socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
