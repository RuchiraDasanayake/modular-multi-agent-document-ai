"""Initialize a fresh, loopback-only native product database and private config.

Run with the gateway Python environment (psycopg required), after installing
official PostgreSQL binaries. This refuses existing configurations/data clusters.
The caller must restrict the runtime directory ACL to the local operator first.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--postgres-port", type=int, default=55432)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--gateway-port", type=int, default=8000)
    args = parser.parse_args()
    root = args.runtime_root.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    pg_bin = args.pg_bin.resolve(strict=True)
    config_path = root / "native-product.json"
    pg_data = root / "postgres-data"
    if config_path.exists() or pg_data.exists():
        raise SystemExit("Refusing to replace an existing native config or PostgreSQL data directory.")
    if len({args.postgres_port, args.frontend_port, args.gateway_port}) != 3 or any(
        not 1024 <= port <= 65535 for port in (args.postgres_port, args.frontend_port, args.gateway_port)
    ):
        raise SystemExit("Use three distinct ports between 1024 and 65535.")
    for name in ("initdb.exe", "pg_ctl.exe", "postgres.exe"):
        if not (pg_bin / name).is_file():
            raise SystemExit(f"Missing PostgreSQL binary: {name}")
    for port in (args.postgres_port, args.frontend_port, args.gateway_port):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    admin_password, app_password = secrets.token_hex(32), secrets.token_hex(32)
    config = {
        "repoRoot": str(repo), "runtimeRoot": str(root), "pgBin": str(pg_bin), "pgData": str(pg_data),
        "postgresPort": args.postgres_port, "frontendPort": args.frontend_port,
        "gatewayPort": args.gateway_port,
        "databaseUrl": f"postgresql://docai_app:{app_password}@127.0.0.1:{args.postgres_port}/docai",
        "maintenanceDatabaseUrl": f"postgresql://docai_admin:{admin_password}@127.0.0.1:{args.postgres_port}/postgres",
        "jwtSecret": secrets.token_hex(48), "adminPassword": secrets.token_urlsafe(24),
        "adminUsername": "admin", "dataDir": str(root / "data"),
        "pythonPath": str(repo / ".venv" / "Scripts" / "python.exe"),
        "gatewayPythonPath": sys.executable,
    }
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def run_pg(*command: str) -> None:
        # Windows postmaster can inherit pg_ctl's output handles. Pipes would keep
        # communicate() waiting after pg_ctl exits; files let us wait on pg_ctl only.
        with (root / "bootstrap-command.log").open("a", encoding="utf-8") as output:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                    creationflags=flags, check=False, timeout=90)
        if result.returncode:
            raise RuntimeError(f"{Path(command[0]).name} failed; see bootstrap-command.log")

    # Keep recovery credentials if initialization is interrupted. Never overwrite them.
    with config_path.open("x", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    pwfile = root / "initdb-password.tmp"
    password_file_created = False
    try:
        with pwfile.open("x", encoding="utf-8") as handle:
            password_file_created = True
            handle.write(admin_password)
        run_pg(str(pg_bin / "initdb.exe"), "-D", str(pg_data), "-U", "docai_admin",
               "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C", f"--pwfile={pwfile}")
    finally:
        if password_file_created:
            pwfile.unlink(missing_ok=True)
    with (pg_data / "postgresql.conf").open("a", encoding="utf-8") as handle:
        handle.write(f"\nlisten_addresses = '127.0.0.1'\nport = {args.postgres_port}\n"
                     "max_connections = 50\nshared_buffers = '128MB'\npassword_encryption = 'scram-sha-256'\n")
    (root / "logs").mkdir(exist_ok=True)
    try:
        run_pg(str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-l", str(root / "logs" / "bootstrap.log"),
               "-w", "-t", "30", "start")
        with psycopg.connect(config["maintenanceDatabaseUrl"], autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE ROLE docai_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE")
                         .format(sql.Literal(app_password)))
            conn.execute("CREATE DATABASE docai OWNER docai_app")
        with psycopg.connect(config["databaseUrl"]) as conn:
            conn.execute((repo / "gateway" / "native_auth.sql").read_text(encoding="utf-8"))
    finally:
        # This directory was created by this invocation. A failed start can still
        # leave its server running; pg_ctl checks this specific cluster's PID.
        if (pg_data / "postmaster.pid").exists():
            run_pg(str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-m", "fast", "-w", "stop")
    print(f"Native database initialized and stopped. Private configuration: {config_path}")


if __name__ == "__main__":
    main()
