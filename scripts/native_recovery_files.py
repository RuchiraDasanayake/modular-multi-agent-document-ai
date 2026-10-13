"""Cold PG16/product snapshot and copy-only recovery. Windows CLI; no database API.

The PowerShell guard supplies process/ACL checks. Failed operations leave an
unsealed directory for inspection; this module never deletes or overwrites it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


class RecoveryError(RuntimeError):
    pass


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (OSError, ValueError) as exc:
        raise RecoveryError("Invalid recovery JSON input.") from exc


def safe_path(path: Path, *, exists: bool = True) -> Path:
    if not path.is_absolute() or path == Path(path.anchor) or path.anchor.startswith("\\\\"):
        raise RecoveryError("An absolute non-root path is required.")
    path = Path(os.path.abspath(path))
    for part in [path, *path.parents]:
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RecoveryError("Reparse points are unsupported in recovery storage.")
    if exists and not path.exists():
        raise RecoveryError("A required recovery input is missing.")
    return path


def separate(paths: list[Path]) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise RecoveryError("Recovery source and destination paths must not overlap.")


def inventory(root: Path) -> dict:
    safe_path(root)
    files, directories = {}, []
    for current, folders, names in os.walk(root, followlinks=False):
        for name in sorted(folders + names):
            path = safe_path(Path(current) / name)
            relative = path.relative_to(root).as_posix()
            info = path.stat()
            if stat.S_ISDIR(info.st_mode):
                directories.append(relative)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                files[relative] = {"bytes": info.st_size, "sha256": digest(path)}
            else:
                raise RecoveryError("Only ordinary files and directories are supported; hardlinks are refused.")
    return {"directories": sorted(directories), "files": dict(sorted(files.items()))}


def copy_inventory(source: Path, destination: Path, expected: dict) -> None:
    destination.mkdir()
    for relative in expected["directories"]:
        (destination / relative).mkdir()
    for relative in expected["files"]:
        source_file = safe_path(source / relative)
        target = destination / relative
        # Exclusive creation plus copyfileobj preserves destination private ACL inheritance.
        with source_file.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    if inventory(destination) != expected:
        raise RecoveryError("Copied files do not match the expected inventory.")


def validate_cluster(cluster: Path) -> None:
    if (cluster / "PG_VERSION").read_text().strip() != "16":
        raise RecoveryError("This cold recovery helper supports PostgreSQL 16 only.")
    for name in ("base", "global", "pg_wal", "pg_xact", "pg_tblspc"):
        if not (cluster / name).is_dir():
            raise RecoveryError("The entire PostgreSQL cluster is required.")
    if any((cluster / "pg_tblspc").iterdir()):
        raise RecoveryError("External PostgreSQL tablespaces are unsupported.")
    if (cluster / "postmaster.pid").exists():
        raise RecoveryError("PostgreSQL is not cleanly stopped or has a stale PID file.")
    if (cluster / "standby.signal").exists() or (cluster / "recovery.signal").exists():
        raise RecoveryError("Standby and archive-recovery clusters are unsupported.")
    # These directives can read/write outside the copied cluster or execute commands.
    forbidden = re.compile(r"^(?:include(?:_dir|_if_exists)?|data_directory|hba_file|ident_file|"
        r"external_pid_file|archive_(?:command|library|mode)|restore_command|recovery_end_command|"
        r"recovery_min_apply_delay|primary_conninfo|primary_slot_name|shared_preload_libraries|"
        r"session_preload_libraries|local_preload_libraries|ssl(?:_\w+)?|log_directory|"
        r"unix_socket_directories)\s*(?:=|\s)", re.I)
    for name in ("postgresql.conf", "postgresql.auto.conf"):
        path = cluster / name
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if forbidden.match(line.strip()):
                    raise RecoveryError("External or executable PostgreSQL configuration is unsupported.")
    for name in ("pg_hba.conf", "pg_ident.conf"):
        path = cluster / name
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                tokens = shlex.split(line, comments=True)
                if tokens and (tokens[0] in {"include", "include_if_exists", "include_dir"} or
                               any(part.startswith("@") for token in tokens for part in token.split(","))):
                    raise RecoveryError("External PostgreSQL authentication includes/name files are unsupported.")


def guard(action: str, path: Path) -> None:
    if os.name != "nt":
        raise RecoveryError("The recovery CLI requires Windows.")
    script = Path(__file__).with_name("native_recovery_guard.ps1")
    try:
        result = subprocess.run(["pwsh", "-NoProfile", "-File", str(script),
            "-Action", action, "-Path", str(path)], capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoveryError("Windows recovery guard did not complete.") from exc
    if result.returncode:
        # Child output may contain private paths or config; keep errors content-free.
        raise RecoveryError(f"Windows recovery {action} guard refused the operation.")


def private_directory(path: Path) -> None:
    safe_path(path, exists=False)
    path.mkdir()  # parent must already exist; never recursively create unknown paths
    guard("Protect", path)


def code_revision(repo: Path) -> str:
    try:
        revision = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=15).stdout.strip()
        subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD"],
            check=True, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryError("Recovery requires a committed, clean tracked checkout.") from exc
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise RecoveryError("Invalid source revision.")
    return revision


def backup(config_path: Path, destination: Path, *, baseline: Path | None = None,
           check=guard, create=private_directory) -> dict:
    config_path, destination = safe_path(config_path), safe_path(destination, exists=False)
    check("Private", config_path)
    config = read_json(config_path)
    cluster, data = safe_path(Path(config["pgData"])), safe_path(Path(config["dataDir"]))
    separate([cluster, data, config_path, destination])
    check("Stopped", config_path)
    validate_cluster(cluster)
    revision = code_revision(Path(config["repoRoot"]))
    before = {"pgdata": inventory(cluster), "data": inventory(data)}
    config_hash = digest(config_path)
    create(destination)
    copy_inventory(cluster, destination / "pgdata", before["pgdata"])
    copy_inventory(data, destination / "data", before["data"])
    private = destination / "private"
    private.mkdir()
    with config_path.open("rb") as src, (private / "native-product.json").open("xb") as dst:
        shutil.copyfileobj(src, dst)
    if baseline is not None:
        baseline = safe_path(baseline)
        check("Private", baseline)
        cases = read_json(baseline)
        if cases.get("kind") != "docai_recovery_http_baseline" or cases.get("dataDir") != str(data):
            raise RecoveryError("HTTP baseline does not identify this data root.")
        for case in cases.get("cases", []):
            source = before["data"]["files"].get(case.get("source_relative_path"))
            if not source or source["sha256"] != case.get("source_sha256"):
                raise RecoveryError("HTTP baseline source changed before cold backup.")
        with baseline.open("rb") as src, (private / "http-baseline.json").open("xb") as dst:
            shutil.copyfileobj(src, dst)
    check("Stopped", config_path)
    if before != {"pgdata": inventory(cluster), "data": inventory(data)} or digest(config_path) != config_hash:
        raise RecoveryError("Source changed during cold backup; the destination remains unsealed.")
    if digest(private / "native-product.json") != config_hash:
        raise RecoveryError("Configuration copy did not verify.")
    check("PrivateTree", destination)
    manifest = {"version": 1, "kind": "docai_pg16_cold_backup", "created_utc":
        datetime.now(timezone.utc).isoformat(), "source": {"pgData": str(cluster), "dataDir": str(data),
        "configPath": str(config_path)}, "code_commit": revision, "payload": inventory(destination),
        "limits": ["same-host dependencies are not backed up", "no tablespaces or external PG configuration",
                   "operator must keep all writers stopped until command returns"]}
    write_new(destination / "manifest.json", manifest)
    seal = {"version": 1, "manifest_sha256": digest(destination / "manifest.json")}
    write_new(destination / "seal.json", seal)
    return seal


def verify_bundle(bundle: Path, *, check=guard) -> dict:
    bundle = safe_path(bundle)
    check("PrivateTree", bundle)
    manifest = read_json(bundle / "manifest.json")
    seal = read_json(bundle / "seal.json")
    if manifest.get("version") != 1 or manifest.get("kind") != "docai_pg16_cold_backup" or \
            seal.get("manifest_sha256") != digest(bundle / "manifest.json"):
        raise RecoveryError("Backup seal is invalid.")
    actual = inventory(bundle)
    for name in ("manifest.json", "seal.json"):
        actual["files"].pop(name, None)
    if actual != manifest.get("payload"):
        raise RecoveryError("Backup inventory does not match its seal.")
    validate_cluster(bundle / "pgdata")
    return manifest


def relocated_jobs(data: Path, original_data: Path) -> list[dict]:
    receipts = []
    folder = data / "frontend" / "jobs"
    if not folder.exists():
        return receipts
    for path in sorted(folder.iterdir()):
        if path.suffix != ".json" or not path.is_file():
            raise RecoveryError("Unexpected job storage entry.")
        record = read_json(path)
        job_id = record.get("jobId")
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", job_id) or path.stem != job_id:
            raise RecoveryError("Job identity does not match its storage filename.")
        if record.get("runPath") or any(run.get("runPath") for run in record.get("runs", []) if isinstance(run, dict)):
            raise RecoveryError("Legacy job runPath values need a separate audited migration.")
        old = record.get("uploadsPath")
        expected = original_data / "frontend" / "uploads" / f"job_{job_id}"
        if not isinstance(old, str) or not Path(old).is_absolute() or Path(os.path.abspath(old)) != expected:
            raise RecoveryError("Unexpected job uploadsPath; global path rewriting is forbidden.")
        new = data / "frontend" / "uploads" / f"job_{job_id}"
        safe_path(new)
        old_hash = digest(path)
        record["uploadsPath"] = str(new)
        # Only this field can change. Use a new side file then atomic replacement in the new restore tree.
        temporary = path.with_suffix(".relocation-new")
        write_new(temporary, record)
        os.replace(temporary, path)
        receipts.append({"path": path.relative_to(data).as_posix(), "field": "uploadsPath",
            "before": old, "after": str(new), "before_sha256": old_hash, "after_sha256": digest(path)})
    return receipts


def clone_config(original: dict, destination: Path, repo: Path, ports: tuple[int, int, int]) -> dict:
    old_ports = {original[k] for k in ("postgresPort", "gatewayPort", "frontendPort")}
    if len(set(ports)) != 3 or any(type(p) is not int or not 1024 <= p <= 65535 or p in old_ports for p in ports):
        raise RecoveryError("Recovery ports must be distinct and different from every original port.")
    if repo == Path(original["repoRoot"]) or repo in Path(original["repoRoot"]).parents or \
            Path(original["repoRoot"]) in repo.parents:
        raise RecoveryError("Passive recovery requires a separate checkout.")
    uri = urlsplit(original["databaseUrl"])
    if uri.scheme not in {"postgres", "postgresql"} or uri.hostname != "127.0.0.1" or \
            uri.port != original["postgresPort"] or uri.query or uri.fragment:
        raise RecoveryError("Only the native loopback PostgreSQL URL is supported.")
    # Preserve credentials in this private file only, never in receipts or stdout.
    authority = uri.netloc.rsplit("@", 1)[0]
    if "@" not in uri.netloc:
        raise RecoveryError("Explicit PostgreSQL credentials are required.")
    result = {key: original[key] for key in ("pgBin", "pythonPath", "gatewayPythonPath", "nodePath",
        "adminUsername", "adminPassword") if key in original}
    result.update(repoRoot=str(repo), runtimeRoot=str(destination), pgData=str(destination / "pgdata"),
        dataDir=str(destination / "data"), postgresPort=ports[0], gatewayPort=ports[1], frontendPort=ports[2],
        databaseUrl=urlunsplit((uri.scheme, f"{authority}@127.0.0.1:{ports[0]}", uri.path, "", "")),
        jwtSecret=secrets.token_urlsafe(48), frontendMode="production", autoOcrEngine="tesseract",
        autoResponseFormat="plain_json", autoLongDocument="reject", autoVisualDocument="disabled",
        recoveryPassive=True)
    return result


def restore(bundle: Path, destination: Path, repo: Path, ports: tuple[int, int, int], *,
            check=guard, create=private_directory) -> dict:
    bundle, destination, repo = safe_path(bundle), safe_path(destination, exists=False), safe_path(repo)
    manifest = verify_bundle(bundle, check=check)
    original = read_json(bundle / "private" / "native-product.json")
    if code_revision(repo) != manifest.get("code_commit"):
        raise RecoveryError("Restore checkout must match the backed-up source revision.")
    originals = [safe_path(Path(manifest["source"][key]), exists=False) for key in ("pgData", "dataDir", "configPath")]
    separate([bundle, destination, *originals])
    separate([repo, destination])
    config = clone_config(original, destination, repo, ports)
    create(destination)
    expected_pg, expected_data = inventory(bundle / "pgdata"), inventory(bundle / "data")
    copy_inventory(bundle / "pgdata", destination / "pgdata", expected_pg)
    copy_inventory(bundle / "data", destination / "data", expected_data)
    relocations = relocated_jobs(destination / "data", Path(manifest["source"]["dataDir"]))
    after = inventory(destination / "data")
    allowed = {r["path"] for r in relocations}
    if after["directories"] != expected_data["directories"] or set(after["files"]) != set(expected_data["files"]) or \
            any(value != after["files"][path] for path, value in expected_data["files"].items() if path not in allowed):
        raise RecoveryError("A non-allowlisted artifact changed during restoration.")
    write_new(destination / "passive-config.json", config)
    receipt = {"version": 1, "kind": "docai_passive_restore", "created_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": str(bundle), "backup_manifest_sha256": digest(bundle / "manifest.json"),
        "destination": str(destination), "repoRoot": str(repo), "ports": list(ports),
        "original_roots": manifest["source"], "relocations": relocations,
        "restored_pgdata": expected_pg, "restored_data": after,
        "config_sha256": digest(destination / "passive-config.json"),
        "workers_started": 0, "provider_keys_copied": False,
        "unchanged_artifacts": "Every data file except the explicitly receipted jobs uploadsPath rewrites"}
    check("PrivateTree", destination)
    write_new(destination / "restore-receipt.json", receipt)
    return {"restore_receipt_sha256": digest(destination / "restore-receipt.json"), "relocated_jobs": len(relocations)}


def verify_restore(destination: Path, *, check=guard) -> dict:
    destination = safe_path(destination)
    check("Private", destination)
    for name in ("pgdata", "data", "passive-config.json", "restore-receipt.json", "state", "logs"):
        if (destination / name).exists():
            check("PrivateTree", destination / name)
    receipt = read_json(destination / "restore-receipt.json")
    if receipt.get("kind") != "docai_passive_restore" or receipt.get("destination") != str(destination) or \
            receipt.get("config_sha256") != digest(destination / "passive-config.json") or \
            receipt.get("restored_pgdata") != inventory(destination / "pgdata") or \
            receipt.get("restored_data") != inventory(destination / "data"):
        raise RecoveryError("Restored data/config changed; this verifier is only for first passive startup.")
    return {"verified": True, "restore_receipt_sha256": digest(destination / "restore-receipt.json")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup_parser = commands.add_parser("backup")
    backup_parser.add_argument("--config", type=Path, required=True)
    backup_parser.add_argument("--destination", type=Path, required=True)
    backup_parser.add_argument("--baseline", type=Path)
    verify_parser = commands.add_parser("verify-backup")
    verify_parser.add_argument("--bundle", type=Path, required=True)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--bundle", type=Path, required=True)
    restore_parser.add_argument("--destination", type=Path, required=True)
    restore_parser.add_argument("--repo", type=Path, required=True)
    restore_parser.add_argument("--ports", type=int, nargs=3, metavar=("PG", "GATEWAY", "FRONTEND"), required=True)
    restored_parser = commands.add_parser("verify-restore")
    restored_parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup(args.config, args.destination, baseline=args.baseline)
        elif args.command == "restore":
            result = restore(args.bundle, args.destination, args.repo, tuple(args.ports))
        elif args.command == "verify-backup":
            verify_bundle(args.bundle)
            result = {"verified": True}
        else:
            result = verify_restore(args.destination)
        print(json.dumps(result))
        return 0
    except (RecoveryError, OSError, KeyError, ValueError):
        # Native configuration contains credentials: never print arbitrary exception text.
        print(json.dumps({"status": "refused", "message": "Recovery precondition or integrity check failed; no existing data was replaced."}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
