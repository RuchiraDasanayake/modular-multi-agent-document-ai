"""Verify acquired TATR bytes without loading a model or processing a PDF."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

REVISIONS = {
    "detection": "microsoft/table-transformer-detection@2357cbe2b5a5d1c03e54f32764f06058933b65ab",
    "structure": "microsoft/table-transformer-structure-recognition-v1.1-all@7587a7ef111d9dcbf8ac695f1376ab7014340a0c",
    "author_notice": "bsmock/TATR-v1.1-All@30e6112ea20d72cc9fb8f443e34ca119d497cfe6",
    "microsoft_source": "microsoft/table-transformer@16d124f616109746b7785f03085100f1f6247575",
}

EXPECTED = {
    "author-notice/README.md": (1744, "11055f915fffabaf71b112bf346ab8732735c9c651bde52f591fec30c904c7fc"),
    "author-notice/revision.txt": (42, "29b77ce55fd78449cd5ad86526915c563cd46fafc21e1381d0205a2b99973056"),
    "detection/config.json": (1228, "ed5b93df2c3a59d473ddea853553a6d545d52bd4e9f8f72bf40b8a974aba4c1d"),
    "detection/model.safetensors": (115317516, "8f1aa73170102c038d40155e2734b343bf07e0fe12594228a8590943b01dccf7"),
    "detection/preprocessor_config.json": (273, "86a8837ae440456b0a9aef788b064921df29c20f0b67040954ce5c2fbd352c4f"),
    "detection/README.md": (1174, "c91e7f8199313c4d24b09e73a2f6df3141268666969346cb7b94ccb59900f5dd"),
    "microsoft-source/docs/INFERENCE.md": (5804, "d4dc7eaca0a8432b3ed9638a7dbe98863ae4e4292822982339f7170609267d3c"),
    "microsoft-source/LICENSE": (1141, "c2cfccb812fe482101a8f04597dfc5a9991a6b2748266c47ac91b6a5aae15383"),
    "microsoft-source/src/inference.py": (38569, "cb7b962f9b984de5ba0b24798ac3f977628bba2d7055da2bf6b4545a31b789e1"),
    "microsoft-source/src/postprocess.py": (37054, "a7b3bdf0b0f9ea4b2ccd04bb0acca4bb05b1809d120edf556526a6d976d027db"),
    "structure/config.json": (76761, "17a8a6edfb9e394263fa6ba9b82176ebccdfcc5d6cd29121ec91572c7d6be22c"),
    "structure/model.safetensors": (115437156, "9df416575a3a36ebd0129342d4f597f14d6e5170268f3d52d28584ab4466a501"),
    "structure/preprocessor_config.json": (374, "eead409bb80e36ae85b8377642c54550f0504f65688ba3a4967950cafe461df2"),
    "structure/README.md": (1056, "01eed360e0f54ad297ab347cfef208d68d8ac2c108b808147bb7af9f8d9132c8"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(root: Path) -> dict[str, object]:
    resolved = root.resolve(strict=True)
    files: list[dict[str, object]] = []
    for name, (size, expected_hash) in EXPECTED.items():
        path = resolved / name
        if not path.resolve(strict=True).is_relative_to(resolved):
            raise ValueError(f"asset escapes root: {name}")
        actual_size, actual_hash = path.stat().st_size, sha256_file(path)
        if actual_size != size or actual_hash != expected_hash:
            raise ValueError(f"asset differs from pinned bytes: {name}")
        files.append({"path": name, "size_bytes": size, "sha256": actual_hash})

    detection = json.loads((resolved / "detection/config.json").read_text(encoding="utf-8"))
    structure = json.loads((resolved / "structure/config.json").read_text(encoding="utf-8"))
    if detection.get("id2label") != {"0": "table", "1": "table rotated"}:
        raise ValueError("detection class map changed")
    if structure.get("id2label") != {
        "0": "table", "1": "table column", "2": "table row",
        "3": "table column header", "4": "table projected row header", "5": "table spanning cell",
    }:
        raise ValueError("structure class map changed")
    packages: dict[str, dict[str, str] | None] = {}
    for name in ("torch", "torchvision", "transformers", "safetensors", "pypdfium2", "Pillow", "numpy"):
        try:
            dist = importlib.metadata.distribution(name)
            record = dist.read_text("RECORD")
            packages[name] = {
                "version": dist.version,
                "record_sha256": hashlib.sha256(record.encode("utf-8")).hexdigest() if record else "unavailable",
            }
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "status": "assets_verified_only",
        "asset_root": str(resolved),
        "revisions": REVISIONS,
        "files": files,
        "package_snapshot": packages,
        "runtime_closure_sealed": False,
        "ocr_word_boxes_sealed": False,
        "cell_postprocessor_sealed": False,
        "document_inference_permitted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    receipt = verify_assets(args.asset_root)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    with os.fdopen(os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
        output.write(encoded)
    print(json.dumps({"receipt": str(args.receipt), "sha256": sha256_file(args.receipt),
                      "asset_count": len(EXPECTED), "status": receipt["status"]}))


if __name__ == "__main__":
    main()
