"""Build the fixed PP-StructureV3 CPU config from verified local model files.

This command performs no network access, package installation, or inference.
It requires separately acquired files from the revisions in the pinned manifest.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError
from product_eval.ppstructure_table_diagnostic import ROOT_FLAGS, active_model_dirs

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = FIXTURES / "PP-StructureV3-v3.7.0.yaml"
MANIFEST = FIXTURES / "ppstructure_v3_3.7.0_models.json"


def file_digest(path: Path, algorithm: str, *, git_blob: bool = False) -> str:
    digest = hashlib.new(algorithm)
    if git_blob:
        digest.update(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    import yaml

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if file_digest(TEMPLATE, "sha256") != manifest["template_sha256"]:
        raise ContractError("PP-StructureV3 upstream template differs from pinned SHA-256")
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    if not isinstance(template, dict) or template.get("pipeline_name") != "PP-StructureV3":
        raise ContractError("invalid pinned PP-StructureV3 template")
    return template, manifest


def verify_model_files(model_root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    if not model_root.is_absolute() or not model_root.is_dir() or model_root.is_symlink():
        raise ContractError("model root must be an existing absolute non-symlink directory")
    model_dirs: dict[str, Path] = {}
    models = manifest.get("models")
    if not isinstance(models, list) or len(models) != 11:
        raise ContractError("pinned manifest must contain eleven models")
    for model in models:
        name = model["model_name"]
        if model["repo_id"] != f"PaddlePaddle/{name}" or model["license"] != "apache-2.0":
            raise ContractError(f"unexpected pinned model source: {name}")
        folder = model_root / name
        if not folder.is_dir() or folder.is_symlink():
            raise ContractError(f"missing regular model directory: {name}")
        expected_files = model["files"]
        if set(expected_files) != {".gitattributes", "README.md", "config.json", "inference.json",
                                   "inference.pdiparams", "inference.yml"}:
            raise ContractError(f"unexpected pinned file inventory: {name}")
        if any(item.is_symlink() for item in folder.rglob("*")):
            raise ContractError(f"model directory contains a symlink: {name}")
        for filename, expected in expected_files.items():
            file = folder / filename
            if not file.is_file() or file.is_symlink() or file.stat().st_size != expected["size_bytes"]:
                raise ContractError(f"missing or wrong-sized pinned model file: {name}/{filename}")
            if "sha256" in expected:
                actual = file_digest(file, "sha256")
                wanted = expected["sha256"]
            else:
                actual = file_digest(file, "sha1", git_blob=True)
                wanted = expected["git_blob_sha1"]
            if actual != wanted:
                raise ContractError(f"pinned model file differs from upstream: {name}/{filename}")
        model_dirs[name] = folder.resolve()
    return model_dirs


def local_config(template: dict[str, Any], model_dirs: dict[str, Path]) -> dict[str, Any]:
    config = copy.deepcopy(template)
    config.update(ROOT_FLAGS)
    modules = config["SubModules"]
    pipelines = config["SubPipelines"]
    active_roots = [modules["LayoutDetection"], modules["RegionDetection"],
                    pipelines["GeneralOCR"], pipelines["TableRecognition"]]
    seen: set[str] = set()

    def assign(node: dict[str, Any]) -> None:
        if "module_name" in node:
            name = node["model_name"]
            if name not in model_dirs:
                raise ContractError(f"active template model is absent from pinned manifest: {name}")
            node["model_dir"] = str(model_dirs[name])
            seen.add(name)
        for key in ("SubModules", "SubPipelines"):
            for child in node.get(key, {}).values():
                assign(child)

    for root in active_roots:
        assign(root)
    if seen != set(model_dirs):
        raise ContractError("pinned model set differs from active default config")
    if set(active_model_dirs(config)) != set(model_dirs.values()):
        raise ContractError("locally configured active model paths differ from the pinned set")
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.exists():
        parser.error("--output must be an unused absolute path")
    try:
        template, manifest = load_sources()
        model_dirs = verify_model_files(args.model_root, manifest)
        config = local_config(template, model_dirs)
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    import yaml

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False, allow_unicode=True)
    print(json.dumps({"config": str(args.output), "active_model_directories": len(model_dirs),
                      "template_sha256": manifest["template_sha256"]}))


if __name__ == "__main__":
    main()
