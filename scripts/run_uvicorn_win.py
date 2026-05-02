"""Run uvicorn with Windows selector event loop policy when needed."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, help="ASGI app path, e.g. gateway.main:app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    run_kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        # Uvicorn's default Windows asyncio loop factory forces Proactor,
        # which psycopg async pools cannot use. Use policy-driven loop instead.
        run_kwargs["loop"] = "none"

    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        **run_kwargs,
    )


if __name__ == "__main__":
    main()
