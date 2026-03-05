"""
Run Directory Cleanup Job
==========================
Removes old run artifacts from the ``runs/`` directory to reclaim disk space.

Each pipeline run creates a UUID-named folder containing intermediate files
(PDFs, JSONs, embeddings, etc.) that are only needed for debugging and
auditing.  This job removes runs older than a configurable retention period.

Usage:
    python -m jobs.cleanup_runs                    # dry-run (default)
    python -m jobs.cleanup_runs --apply            # actually delete
    python -m jobs.cleanup_runs --all              # remove every run
    python -m jobs.cleanup_runs --max-age-days 7   # keep only last 7 days
    python -m jobs.cleanup_runs --keep-latest 20   # always keep 20 most recent

Author: Cleanup Utility
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

RUNS_DIR = Path(os.getenv("RUNS_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs"
)))

DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_KEEP_LATEST = 10

def _get_run_mtime(run_path: Path) -> datetime:
    """Return the most recent modification time across all files in a run."""
    latest = 0.0
    for root, _dirs, files in os.walk(run_path):
        for f in files:
            try:
                mt = os.path.getmtime(os.path.join(root, f))
                if mt > latest:
                    latest = mt
            except OSError:
                pass
    return datetime.fromtimestamp(latest) if latest else datetime.min

def _dir_size_mb(path: Path) -> float:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 * 1024)

def cleanup_runs(
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    keep_latest: int = DEFAULT_KEEP_LATEST,
    dry_run: bool = True,
    remove_pdfs_only: bool = False,
    remove_all: bool = False,
) -> dict:
    """
    Clean up old run directories.

    Parameters
    ----------
    max_age_days : int
        Runs older than this many days are eligible for removal.
    keep_latest : int
        Always keep at least this many of the most recent runs.
    dry_run : bool
        If True, print what would be deleted without actually deleting.
    remove_pdfs_only : bool
        If True, only remove duplicate PDFs (the biggest space waster)
        instead of deleting entire run folders.
    remove_all : bool
        If True, remove every run regardless of age or keep_latest.

    Returns
    -------
    dict with summary statistics.
    """
    if not RUNS_DIR.is_dir():
        logger.warning("Runs directory not found: %s", RUNS_DIR)
        return {"error": "runs_dir_not_found"}

    # Gather all run directories (UUID-named folders)
    runs = []
    for entry in RUNS_DIR.iterdir():
        if entry.is_dir() and len(entry.name) == 32:
            mtime = _get_run_mtime(entry)
            size_mb = _dir_size_mb(entry)
            runs.append((entry, mtime, size_mb))

    runs.sort(key=lambda x: x[1], reverse=True)  # newest first

    cutoff = datetime.now() - timedelta(days=max_age_days)
    total_runs = len(runs)
    kept = 0
    removed = 0
    freed_mb = 0.0

    logger.info("Found %d runs in %s", total_runs, RUNS_DIR)
    logger.info("Retention: %d days, keep latest %d", max_age_days, keep_latest)
    logger.info("Cutoff date: %s", cutoff.strftime('%Y-%m-%d %H:%M'))
    logger.info("Mode: %s", 'DRY RUN' if dry_run else 'APPLY')
    if remove_all:
        logger.info("Strategy: Remove ALL runs")
    elif remove_pdfs_only:
        logger.info("Strategy: Remove duplicate PDFs only")

    for idx, (run_path, mtime, size_mb) in enumerate(runs):
        if not remove_all:
            # Always keep the N most recent
            if idx < keep_latest:
                kept += 1
                continue

            # Keep if newer than cutoff
            if mtime > cutoff:
                kept += 1
                continue

        # This run is eligible for cleanup
        if remove_pdfs_only:
            # Only remove PDFs from input/original
            pdf_freed = _remove_pdfs(run_path, dry_run)
            if pdf_freed > 0:
                freed_mb += pdf_freed
                removed += 1
        else:
            if dry_run:
                logger.info("WOULD DELETE: %s (%.1f MB, modified %s)",
                            run_path.name, size_mb, mtime.strftime('%Y-%m-%d'))
            else:
                try:
                    shutil.rmtree(run_path)
                    logger.info("DELETED: %s (%.1f MB)", run_path.name, size_mb)
                except OSError as e:
                    logger.error("Error deleting %s: %s", run_path.name, e)
                    continue
            freed_mb += size_mb
            removed += 1

    summary = {
        "total_runs": total_runs,
        "kept": kept,
        "removed": removed,
        "freed_mb": round(freed_mb, 1),
        "dry_run": dry_run,
    }
    action = "Would free" if dry_run else "Freed"
    logger.info("Kept: %d | Removed: %d | %s: %.1f MB", kept, removed, action, freed_mb)

    if dry_run and removed > 0:
        logger.info("Re-run with --apply to actually delete these runs.")

    return summary

def _remove_pdfs(run_path: Path, dry_run: bool) -> float:
    """Remove only PDF files from a run directory. Returns MB freed."""
    freed = 0.0
    for root, _dirs, files in os.walk(run_path):
        for f in files:
            if f.lower().endswith(".pdf"):
                fp = Path(root) / f
                size = fp.stat().st_size / (1024 * 1024)
                if dry_run:
                    logger.info("WOULD REMOVE PDF: %s (%.1f MB)", fp.relative_to(run_path), size)
                else:
                    fp.unlink()
                    logger.info("REMOVED PDF: %s (%.1f MB)", fp.relative_to(run_path), size)
                freed += size
    return freed

def main():
    parser = argparse.ArgumentParser(
        description="Clean up old pipeline run directories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
        help=f"Remove runs older than N days (default: {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument(
        "--keep-latest", type=int, default=DEFAULT_KEEP_LATEST,
        help=f"Always keep the N most recent runs (default: {DEFAULT_KEEP_LATEST})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete (default is dry-run)",
    )
    parser.add_argument(
        "--pdfs-only", action="store_true",
        help="Only remove duplicate PDFs instead of entire folders",
    )
    parser.add_argument(
        "--all", dest="remove_all", action="store_true",
        help="Remove every run regardless of age or keep-latest",
    )
    args = parser.parse_args()

    cleanup_runs(
        max_age_days=args.max_age_days,
        keep_latest=args.keep_latest,
        dry_run=not args.apply,
        remove_pdfs_only=args.pdfs_only,
        remove_all=args.remove_all,
    )

if __name__ == "__main__":
    main()
