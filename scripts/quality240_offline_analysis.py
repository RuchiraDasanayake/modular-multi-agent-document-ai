"""Isolate post-seal analysis from later product changes; never modify a campaign.

Scope: research_evidence / keep. Prepare copies exactly the registered Python
sources and five separately recorded analysis modules into a new external tree.
Preflight checks the unchanged frozen-module guard without reading predictions
or labels. Verify reads sealed predictions only; score additionally requires the
independently pinned verification receipt before invoking the existing scorer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True

ANALYSIS_MODULES = (
    "product_eval/quality_scoring.py", "product_eval/quality_scoring_verification.py",
    "product_eval/paired_uncertainty.py", "product_eval/quality_transport.py",
    "product_eval/quality_http408_resolution.py",
)
MANIFEST = "analysis-tree.json"
SHA = re.compile(r"[a-f0-9]{64}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, raw: bytes) -> str:
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest(raw)


def encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def checked_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    require(bool(name) and not relative.is_absolute() and relative.as_posix() == name
            and not {".", ".."}.intersection(relative.parts) and ":" not in name and "\\" not in name,
            "Unsafe analysis source path")
    path = root.joinpath(*relative.parts)
    require(not any(parent.is_symlink() for parent in (path, *path.parents)) and path.is_file(),
            "Missing or symlinked analysis source")
    return path


def protocol_at(run: Path, expected: str) -> dict:
    raw = checked_path(run, "protocol.json").read_bytes()
    require(bool(SHA.fullmatch(expected)) and digest(raw) == expected, "Protocol hash differs")
    protocol = json.loads(raw)
    require(protocol.get("mode") == "paired_quality240" and protocol.get("version") == 1
            and protocol.get("labels_opened") is False, "Unknown paired analysis protocol")
    return protocol


def prepare(frozen_root: Path, run: Path, protocol_sha: str, analysis_root: Path) -> dict:
    """Stage code only. No document, prediction, reference or database access."""
    frozen_root, run, analysis_root = (path.resolve() for path in (frozen_root, run, analysis_root))
    current = Path(__file__).resolve().parents[1]
    require(not analysis_root.exists() and all(not analysis_root.is_relative_to(root)
            for root in (frozen_root, run, current)), "New external analysis directory required")
    protocol = protocol_at(run, protocol_sha)
    registered = protocol["code"]["python_source_sha256"]
    require(isinstance(registered, dict) and bool(registered), "Registered source files required")
    require(not set(ANALYSIS_MODULES).intersection(registered), "Analysis overlay would replace a frozen source")
    actual = {path.relative_to(frozen_root).as_posix() for package in ("idpo", "product_eval")
              for path in (frozen_root / package).rglob("*.py")}
    require(actual == set(registered), "Frozen source tree has missing or additional Python modules")
    payloads = {}
    for name, expected in registered.items():
        require(name.startswith(("idpo/", "product_eval/")) and name.endswith(".py")
                and isinstance(expected, str) and bool(SHA.fullmatch(expected)), "Invalid frozen module registration")
        raw = checked_path(frozen_root, name).read_bytes()
        require(digest(raw) == expected, "Frozen source bytes differ from the execution registration")
        payloads[name] = raw
    analysis = {}
    for name in ANALYSIS_MODULES:
        payloads[name] = checked_path(current, name).read_bytes()
        analysis[name] = digest(payloads[name])
    # Validate everything before creating output; an interrupted copy has no
    # manifest and cannot be imported. Choose a fresh directory after that case.
    analysis_root.mkdir(parents=True, exist_ok=False)
    for name, raw in payloads.items():
        path = analysis_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new(path, raw)
    manifest = {"version": 1, "type": "quality240_offline_analysis_tree", "protocol_sha256": protocol_sha,
        "registered_commit": protocol["code"]["commit"], "frozen_modules_sha256": registered,
        "analysis_modules_sha256": analysis, "loader_sha256": digest(Path(__file__).read_bytes()),
        "labels_opened": False, "prediction_contents_read": False, "model_calls": 0}
    sha = write_new(analysis_root / MANIFEST, encoded(manifest))
    return {"analysis_tree_sha256": sha, "frozen_modules": len(registered), "analysis_modules": len(analysis),
            "model_calls": 0, "labels_opened": False}


def validate_tree(analysis_root: Path, expected: str, run: Path, protocol_sha: str) -> tuple[dict, dict]:
    raw = checked_path(analysis_root, MANIFEST).read_bytes()
    require(bool(SHA.fullmatch(expected)) and digest(raw) == expected, "Analysis tree manifest hash differs")
    manifest, protocol = json.loads(raw), protocol_at(run, protocol_sha)
    require(manifest["version"] == 1 and manifest["type"] == "quality240_offline_analysis_tree"
            and manifest["protocol_sha256"] == protocol_sha and manifest["registered_commit"] == protocol["code"]["commit"]
            and manifest["labels_opened"] is False and manifest["prediction_contents_read"] is False
            and manifest["model_calls"] == 0, "Analysis tree binding differs")
    require(manifest["frozen_modules_sha256"] == protocol["code"]["python_source_sha256"]
            and set(manifest["analysis_modules_sha256"]) == set(ANALYSIS_MODULES)
            and not set(manifest["frozen_modules_sha256"]).intersection(ANALYSIS_MODULES),
            "Frozen source or analysis module inventory differs")
    require(manifest["loader_sha256"] == digest(Path(__file__).read_bytes()), "Offline loader implementation changed")
    files = {**manifest["frozen_modules_sha256"], **manifest["analysis_modules_sha256"]}
    for name, sha in files.items():
        require(isinstance(sha, str) and bool(SHA.fullmatch(sha))
                and digest(checked_path(analysis_root, name).read_bytes()) == sha, "Staged analysis source hash differs")
    actual = set()
    for path in analysis_root.rglob("*"):
        require(not path.is_symlink(), "Analysis tree symlink is unsupported")
        if path.is_file():
            actual.add(path.relative_to(analysis_root).as_posix())
    require(actual == set(files) | {MANIFEST}, "Unexpected or missing staged analysis artifact")
    return manifest, protocol


def activate(analysis_root: Path):
    require(not any(name in {"idpo", "product_eval"} or name.startswith(("idpo.", "product_eval.")) for name in sys.modules),
            "Product modules were imported before isolation")
    # Preserve only the selected interpreter's standard library/dependencies.
    # PYTHONPATH, the invocation directory and the changed product checkout must
    # not supply a missing frozen module. No bytecode is written to the tree.
    prefixes = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
    sys.path[:] = [str(analysis_root.resolve())] + [value for value in sys.path if value and
        any(Path(value).resolve().is_relative_to(prefix) for prefix in prefixes)]
    importlib.invalidate_caches()
    verifier = importlib.import_module("product_eval.quality_scoring_verification")
    verify_import_origins(analysis_root)
    return verifier


def verify_import_origins(analysis_root: Path) -> None:
    for name, module in list(sys.modules.items()):
        if name in {"idpo", "product_eval"} or name.startswith(("idpo.", "product_eval.")):
            require(bool(getattr(module, "__file__", None)) and Path(module.__file__).resolve().is_relative_to(analysis_root.resolve()),
                    "A product or scoring module escaped the isolated tree")


def verification_context(args) -> dict:
    return {"analysis_tree_sha256": args.analysis_sha256, "protocol_sha256": args.protocol_sha256,
            "prediction_seal_sha256": args.prediction_seal_sha256,
            "transport_amendment_sha256": args.transport_amendment_sha256,
            "http408_resolution_sha256": sorted(args.http408_resolution_sha256)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "preflight", "verify", "score"))
    for name in ("run", "analysis-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--protocol-sha256", required=True)
    for name in ("frozen-root", "output", "verification-receipt", "vrdu-root", "cord-gold"):
        parser.add_argument("--" + name, type=Path)
    for name in ("analysis-sha256", "prediction-seal-sha256", "transport-amendment-sha256", "verification-sha256"):
        parser.add_argument("--" + name)
    parser.add_argument("--http408-resolution-sha256", action="append", default=[])
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.frozen_root:
            parser.error("prepare requires --frozen-root")
        result = prepare(args.frozen_root, args.run, args.protocol_sha256, args.analysis_root)
    else:
        if not args.analysis_sha256:
            parser.error("An independently retained --analysis-sha256 is required")
        _, protocol = validate_tree(args.analysis_root, args.analysis_sha256, args.run, args.protocol_sha256)
        verifier = activate(args.analysis_root)
        frozen = verifier.verify_frozen_modules(protocol)
        if args.action == "preflight":
            result = {"analysis_tree_sha256": args.analysis_sha256, "verified_frozen_modules": frozen,
                      "prediction_contents_read": False, "labels_opened": False, "model_calls": 0}
        else:
            if not args.prediction_seal_sha256 or not args.output:
                parser.error("verify/score requires --prediction-seal-sha256 and a new external --output")
            require(not args.output.exists() and not args.output.resolve().is_relative_to(args.run.resolve())
                    and not args.output.resolve().is_relative_to(args.analysis_root.resolve()), "New external output required")
            context = verification_context(args)
            if args.action == "verify":
                bundle = verifier.verify_campaign(args.run, args.prediction_seal_sha256,
                    transport_amendment_sha256=args.transport_amendment_sha256,
                    http408_resolution_sha256=args.http408_resolution_sha256)
                verify_import_origins(args.analysis_root)
                receipt = {"version": 1, "type": "quality240_independent_prediction_verification",
                           "context": context, "verification": bundle["receipt"], "labels_opened": False}
                result = {"verification_sha256": write_new(args.output, encoded(receipt)),
                          "labels_opened": False, "model_calls": 0}
            else:
                if not all((args.verification_receipt, args.verification_sha256, args.vrdu_root, args.cord_gold)):
                    parser.error("score requires the independent verification receipt/hash and both reference paths")
                raw = args.verification_receipt.read_bytes()
                require(bool(SHA.fullmatch(args.verification_sha256)) and digest(raw) == args.verification_sha256,
                        "Independent verification receipt hash differs")
                receipt = json.loads(raw)
                require(receipt.get("version") == 1 and receipt.get("type") == "quality240_independent_prediction_verification"
                        and receipt.get("context") == context and receipt.get("labels_opened") is False,
                        "Independent verification context differs")
                scorer = importlib.import_module("product_eval.quality_scoring")
                verify_import_origins(args.analysis_root)
                result = scorer.run_analysis(args.run, args.prediction_seal_sha256, args.output,
                    vrdu_root=args.vrdu_root, cord_gold=args.cord_gold,
                    transport_amendment_sha256=args.transport_amendment_sha256,
                    http408_resolution_sha256=args.http408_resolution_sha256)
        verify_import_origins(args.analysis_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
