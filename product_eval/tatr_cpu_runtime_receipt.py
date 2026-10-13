"""Record an offline, synthetic-only CPU compatibility check for pinned TATR.

This research tool never opens a PDF or uses gold labels. The resulting lock
records installed package RECORD digests and bundled notice files; it is not
a product packaging approval or a table-cell quality measurement.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import sys
import tarfile
import time
import zipfile
from collections import Counter
from pathlib import Path

from product_eval.tatr_asset_preflight import sha256_file, verify_assets
from product_eval.tatr_output_adapter import CLASS_LABELS, adapt_detr_outputs

GIB = 1024**3
UNUSED_DETECTION_BUFFERS = {
    f"model.backbone.conv_encoder.model.layer{layer}.0.downsample.1.num_batches_tracked"
    for layer in (2, 3, 4)
}
TOKENIZERS_SDIST_SHA256 = "473b83b915e547aa366d1eee11806deaf419e17be16310ac0a14077f1e28f917"
TOKENIZERS_LICENSE_MEMBER = "tokenizers-0.22.2/tokenizers/LICENSE"
TORCHVISION_WHEEL_SHA256 = "783c8fc580bbfc159bff52f4f72cdd538e42b32956e70dffa42b940db114e151"


def _write_new(path: Path, value: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return sha256_file(path)


def _notice_files(dist: importlib.metadata.Distribution) -> list[dict[str, object]]:
    notices: list[dict[str, object]] = []
    for entry in dist.files or ():
        relative = str(entry).replace("\\", "/")
        name = Path(relative).name.lower()
        if ("/licenses/" not in relative.lower()
                and not name.startswith(("license", "licence", "notice", "copying", "copyright"))):
            continue
        path = Path(dist.locate_file(entry))
        if path.is_file():
            notices.append({
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            })
    return sorted(notices, key=lambda item: str(item["path"]))


def _verify_installed_record(
    dist: importlib.metadata.Distribution, record: str, runtime_root: Path | None = None
) -> tuple[int, int, int, str, set[Path], int]:
    runtime_root = (runtime_root or Path(sys.prefix)).resolve()
    verified = bytecode = unhashed_payload = 0
    bytecode_files: list[tuple[str, str, int]] = []
    owned_paths: set[Path] = set()
    record_self_paths: set[Path] = set()
    seen_rows: dict[Path, tuple[str, str, str]] = {}
    duplicate_aliases = 0
    for name, encoded_hash, size in csv.reader(io.StringIO(record)):
        path = Path(dist.locate_file(name)).resolve()
        previous = seen_rows.get(path)
        if previous is not None:
            previous_name, previous_hash, previous_size = previous
            allowed_torchvision_alias = (
                dist.metadata["Name"].lower() == "torchvision"
                and "\\" in name and "\\" not in previous_name
                and not previous_hash and not previous_size
                and (bool(encoded_hash) or name.replace("\\", "/").endswith("/RECORD"))
            )
            if not allowed_torchvision_alias:
                raise ValueError(f"duplicate installed RECORD path: {name}")
            duplicate_aliases += 1
        else:
            seen_rows[path] = (name, encoded_hash, size)
        if not path.is_relative_to(runtime_root) or not path.is_file():
            raise ValueError(f"installed RECORD path missing or escaped: {name}")
        owned_paths.add(path)
        if not encoded_hash:
            normalized = name.replace("\\", "/")
            if normalized.endswith("/RECORD"):
                record_self_paths.add(path)
                continue  # RECORD cannot hash itself.
            if normalized.endswith(".pyc"):
                bytecode += 1
                bytecode_files.append((normalized, sha256_file(path), path.stat().st_size))
            else:
                unhashed_payload += 1
            continue
        algorithm, digest = encoded_hash.split("=", 1)
        if algorithm != "sha256":
            raise ValueError(f"unsupported RECORD digest for {dist.metadata['Name']}: {algorithm}")
        if not path.is_file() or (size and path.stat().st_size != int(size)):
            raise ValueError(f"installed file differs from wheel RECORD: {name}")
        expected = base64.urlsafe_b64decode(digest + "===").hex()
        if sha256_file(path) != expected:
            raise ValueError(f"installed file hash differs from wheel RECORD: {name}")
        verified += 1
    if len(record_self_paths) != 1:
        raise ValueError(f"installed distribution has {len(record_self_paths)} RECORD self paths")
    bytecode_digest = hashlib.sha256(json.dumps(
        sorted(bytecode_files), separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")).hexdigest()
    return verified, bytecode, unhashed_payload, bytecode_digest, owned_paths, duplicate_aliases


def _raw_installed_record(dist: importlib.metadata.Distribution) -> bytes:
    records = {Path(dist.locate_file(entry)).resolve() for entry in dist.files or ()
               if len(Path(str(entry)).parts) == 2
               and str(entry).replace("\\", "/").endswith(".dist-info/RECORD")}
    if len(records) != 1:
        raise ValueError(f"expected one raw installed RECORD: {dist.metadata['Name']}")
    return next(iter(records)).read_bytes()


def _verify_site_packages_inventory(site_packages: Path, owned_paths: set[Path]) -> int:
    if not site_packages.is_dir():
        raise ValueError(f"missing site-packages directory: {site_packages}")
    actual = {path.resolve() for path in site_packages.rglob("*") if path.is_file()}
    unowned = actual - owned_paths
    if unowned:
        raise ValueError(f"unowned installed site-packages file: {min(unowned)}")
    return len(actual)


def _verify_torchvision_wheel(path: Path) -> int:
    if sha256_file(path) != TORCHVISION_WHEEL_SHA256:
        raise ValueError("torchvision wheel differs from pinned PyTorch index digest")
    dist = importlib.metadata.distribution("torchvision")
    checked = 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir() or member.filename.endswith("/RECORD"):
                continue
            installed = Path(dist.locate_file(member.filename))
            if not installed.is_file():
                raise ValueError(f"torchvision wheel member is missing: {member.filename}")
            if hashlib.sha256(archive.read(member)).hexdigest() != sha256_file(installed):
                raise ValueError(f"torchvision wheel member differs: {member.filename}")
            checked += 1
    return checked


def _runtime_lock(
    asset_root: Path, tokenizers_sdist: Path, torchvision_wheel: Path
) -> dict[str, object]:
    asset_receipt = verify_assets(asset_root)
    for card in ("detection/README.md", "structure/README.md", "author-notice/README.md"):
        if "license: mit" not in (asset_root / card).read_text(encoding="utf-8").lower():
            raise ValueError(f"pinned model card has no MIT declaration: {card}")
    if "MIT License" not in (asset_root / "microsoft-source/LICENSE").read_text(encoding="utf-8"):
        raise ValueError("pinned Microsoft source notice has no MIT declaration")

    packages: list[dict[str, object]] = []
    owned_paths: set[Path] = set()
    for dist in importlib.metadata.distributions():
        record_bytes = _raw_installed_record(dist)
        verified, bytecode, unhashed_payload, bytecode_digest, distribution_paths, aliases = (
            _verify_installed_record(dist, record_bytes.decode("utf-8"))
        )
        duplicate_owned = owned_paths & distribution_paths
        if duplicate_owned:
            raise ValueError(f"installed RECORD paths have duplicate owners: {min(duplicate_owned)}")
        owned_paths.update(distribution_paths)
        if unhashed_payload and dist.metadata["Name"].lower() != "torchvision":
            raise ValueError(f"unhashed wheel payload outside torchvision: {dist.metadata['Name']}")
        notices = _notice_files(dist)
        packages.append({
            "name": dist.metadata["Name"],
            "version": dist.version,
            "record_sha256": hashlib.sha256(record_bytes).hexdigest(),
            "record_verified_files": verified,
            "record_unhashed_bytecode_files": bytecode,
            "record_unhashed_bytecode_sha256": bytecode_digest,
            "record_unhashed_payload_files": unhashed_payload,
            "record_duplicate_path_aliases": aliases,
            "license_expression": dist.metadata.get("License-Expression"),
            "license_classifiers": sorted(
                value for value in dist.metadata.get_all("Classifier", [])
                if value.startswith("License ::")
            ),
            "notices": notices,
        })
    packages.sort(key=lambda item: str(item["name"]).lower())
    site_packages_file_count = _verify_site_packages_inventory(
        Path(sys.prefix) / "Lib" / "site-packages", owned_paths
    )
    names = {str(item["name"]).lower().replace("_", "-") for item in packages}
    required = {
        "torch", "torchvision", "timm", "transformers", "safetensors",
        "pillow", "numpy", "pypdfium2", "psutil",
    }
    if not required <= names:
        raise ValueError(f"runtime is missing required packages: {sorted(required - names)}")
    torchvision_checked = _verify_torchvision_wheel(torchvision_wheel)
    no_notices = {str(item["name"]).lower() for item in packages if not item["notices"]}
    if no_notices != {"tokenizers"}:
        raise ValueError(f"unexpected packages without bundled notices: {sorted(no_notices)}")
    if sha256_file(tokenizers_sdist) != TOKENIZERS_SDIST_SHA256:
        raise ValueError("tokenizers source distribution differs from pinned PyPI digest")
    with tarfile.open(tokenizers_sdist, "r:gz") as archive:
        member = archive.getmember(TOKENIZERS_LICENSE_MEMBER)
        if not member.isfile():
            raise ValueError("tokenizers source notice is not a file")
        with archive.extractfile(member) as stream:
            license_bytes = stream.read()
    if not license_bytes.lstrip().startswith(b"Apache License"):
        raise ValueError("tokenizers source notice is not Apache 2.0")
    return {
        "status": "synthetic_cpu_runtime_only",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "asset_revisions": asset_receipt["revisions"],
        "assets": asset_receipt["files"],
        "packages": packages,
        "site_packages_file_count": site_packages_file_count,
        "site_packages_unowned_files": 0,
        "supplemental_notices": [{
            "package": "tokenizers==0.22.2",
            "source_url": "https://pypi.org/project/tokenizers/0.22.2/",
            "source_sdist_sha256": TOKENIZERS_SDIST_SHA256,
            "member": TOKENIZERS_LICENSE_MEMBER,
            "sha256": hashlib.sha256(license_bytes).hexdigest(),
            "size_bytes": len(license_bytes),
        }],
        "supplemental_wheels": [{
            "package": "torchvision==0.25.0+cpu",
            "source_url": "https://download.pytorch.org/whl/cpu/torchvision/",
            "sha256": TORCHVISION_WHEEL_SHA256,
            "verified_installed_members": torchvision_checked,
        }],
        "document_inference_permitted": False,
    }


def _resource_snapshot(host_disk_root: Path, data_disk_root: Path) -> dict[str, float]:
    import psutil

    available = psutil.virtual_memory().available / GIB
    host_free = psutil.disk_usage(str(host_disk_root)).free / GIB
    data_free = psutil.disk_usage(str(data_disk_root)).free / GIB
    if available < 6 or host_free < 4 or data_free < 4:
        raise RuntimeError("TATR synthetic smoke resource floor not met")
    return {"available_ram_gib": round(available, 3),
            "free_host_disk_gib": round(host_free, 3),
            "free_data_disk_gib": round(data_free, 3)}


def _synthetic_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (512, 384), "white")
    draw = ImageDraw.Draw(image)
    for row in range(5):
        y = 50 + row * 65
        draw.line((32, y, 480, y), fill="black", width=2)
    for column in range(5):
        x = 32 + column * 112
        draw.line((x, 50, x, 310), fill="black", width=2)
    for row in range(4):
        for column in range(4):
            draw.text((40 + column * 112, 72 + row * 65), f"R{row}C{column}", fill="black")
    return image


def _model_smoke(kind: str, model_root: Path, image) -> dict[str, object]:
    import psutil
    import torch
    from PIL import Image
    from torchvision.transforms import Normalize, ToTensor
    from transformers import (
        DetrImageProcessor,
        TableTransformerConfig,
        TableTransformerForObjectDetection,
    )

    config = TableTransformerConfig.from_pretrained(model_root, local_files_only=True)
    config.use_pretrained_backbone = False  # Full safetensors replace initialization; no external ResNet download.
    load_start = time.perf_counter()
    model, loading = TableTransformerForObjectDetection.from_pretrained(
        model_root, config=config, local_files_only=True, use_safetensors=True,
        trust_remote_code=False, output_loading_info=True,
    )
    load_seconds = time.perf_counter() - load_start
    expected_unused = UNUSED_DETECTION_BUFFERS if kind == "detection" else set()
    if (loading["missing_keys"] or loading.get("mismatched_keys")
            or set(loading["unexpected_keys"]) != expected_unused):
        raise RuntimeError(f"{kind} safetensors have unexpected load differences: {loading}")
    if tuple(config.id2label[index] for index in range(len(CLASS_LABELS[kind]))) != CLASS_LABELS[kind]:
        raise RuntimeError(f"{kind} class map differs from pinned adapter")

    processor = DetrImageProcessor.from_pretrained(model_root, local_files_only=True)
    longest_edge = 800 if kind == "detection" else 1000
    scale = longest_edge / max(image.size)
    resized = {"width": round(image.width * scale), "height": round(image.height * scale)}
    encode_start = time.perf_counter()
    inputs = processor(image, size=resized, resample=Image.Resampling.BICUBIC, return_tensors="pt")
    encode_seconds = time.perf_counter() - encode_start
    official_pixels = Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])(
        ToTensor()(image.resize((resized["width"], resized["height"])))
    )
    if tuple(inputs["pixel_values"].shape[2:]) != tuple(official_pixels.shape[1:]):
        raise RuntimeError(f"{kind} processor padding changed synthetic image dimensions")
    preprocess_delta = (inputs["pixel_values"][0] - official_pixels).abs().max().item()
    if preprocess_delta > 1e-6:
        raise RuntimeError(f"{kind} preprocessing differs from pinned MaxResize and normalization")
    model.eval().to("cpu")
    infer_start = time.perf_counter()
    with torch.inference_mode():
        output = model(**inputs)
    infer_seconds = time.perf_counter() - infer_start
    logits = output.logits[0].tolist()
    boxes = output.pred_boxes[0].tolist()
    adapted = adapt_detr_outputs(logits, boxes, image.size, model_kind=kind)
    expected_shape = (1, config.num_queries, len(CLASS_LABELS[kind]) + 1)
    if tuple(output.logits.shape) != expected_shape or tuple(output.pred_boxes.shape) != (1, config.num_queries, 4):
        raise RuntimeError(f"{kind} tensor shape differs from pinned config")
    hf_boxes = processor.post_process_object_detection(
        output, threshold=0.0, target_sizes=[(image.height, image.width)]
    )[0]["boxes"].tolist()
    if len(hf_boxes) != len(adapted):
        raise RuntimeError(f"{kind} Hugging Face box count differs from raw queries")
    box_delta = max(abs(x - y) for raw, hf in zip(adapted, hf_boxes, strict=True)
                    for x, y in zip(raw["bbox"], hf, strict=True))
    if box_delta > 1e-3:
        raise RuntimeError(f"{kind} adapter box coordinates differ from Hugging Face")
    counts = Counter(str(item["label"]) for item in adapted)
    active = sorted((item for item in adapted if item["above_frozen_threshold"]),
                    key=lambda item: float(item["score"]), reverse=True)
    memory = psutil.Process().memory_info()
    return {
        "kind": kind, "image_size": list(image.size), "resized_image_size": resized,
        "processor_pinned_size": processor.size, "resample": "Pillow BICUBIC",
        "input_shape": list(inputs["pixel_values"].shape),
        "official_preprocess_max_abs_delta": preprocess_delta,
        "logits_shape": list(output.logits.shape), "pred_boxes_shape": list(output.pred_boxes.shape),
        "query_count": len(adapted), "argmax_classes": dict(sorted(counts.items())),
        "above_0_5_count": len(active), "top_active_queries": active[:3],
        "adapter_vs_hf_max_box_delta_pixels": box_delta,
        "missing_keys": loading["missing_keys"],
        "unexpected_keys": sorted(loading["unexpected_keys"]),
        "mismatched_keys": loading.get("mismatched_keys", []),
        "load_seconds": round(load_seconds, 3), "encode_seconds": round(encode_seconds, 3),
        "forward_seconds": round(infer_seconds, 3),
        "rss_mb": round(memory.rss / 1e6, 1),
        "process_peak_working_set_mb": round(memory.peak_wset / 1e6, 1),
        "model_device": str(next(model.parameters()).device),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--host-disk-root", required=True, type=Path)
    parser.add_argument("--data-disk-root", required=True, type=Path)
    parser.add_argument("--tokenizers-sdist", required=True, type=Path)
    parser.add_argument("--torchvision-wheel", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--lock-out", required=True, type=Path)
    parser.add_argument("--expected-lock", type=Path)
    args = parser.parse_args()
    os.environ["HF_HOME"] = str(args.cache_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    resources_before = _resource_snapshot(args.host_disk_root, args.data_disk_root)
    lock_start = time.perf_counter()
    lock = _runtime_lock(args.asset_root, args.tokenizers_sdist, args.torchvision_wheel)
    inventory_seconds = time.perf_counter() - lock_start
    if args.expected_lock and lock != json.loads(args.expected_lock.read_text(encoding="utf-8")):
        raise RuntimeError("installed runtime differs from expected lock")
    import torch

    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    image = _synthetic_image()
    image_digest = hashlib.sha256(image.tobytes()).hexdigest()
    detection = _model_smoke("detection", args.asset_root / "detection", image)
    resources_between = _resource_snapshot(args.host_disk_root, args.data_disk_root)
    structure = _model_smoke("structure", args.asset_root / "structure", image.crop((32, 50, 480, 310)))
    resources_after = _resource_snapshot(args.host_disk_root, args.data_disk_root)
    lock_sha256 = _write_new(args.lock_out, lock)
    receipt: dict[str, object] = {
        "status": "synthetic_cpu_compat_pass",
        "selected_pdf_or_gold_opened": False,
        "document_inference_permitted": False,
        "runtime_lock_sha256": lock_sha256,
        "asset_root": str(args.asset_root.resolve(strict=True)),
        "python_executable": sys.executable,
        "provider": "PyTorch CPU eager",
        "torch_cuda_available": torch.cuda.is_available(),
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "synthetic_image_sha256_rgb_bytes": image_digest,
        "resource_before": resources_before,
        "resource_between": resources_between,
        "resource_after": resources_after,
        "asset_and_runtime_inventory_seconds": round(inventory_seconds, 3),
        "models": [detection, structure],
    }
    _write_new(args.receipt, receipt)
    print(json.dumps({"receipt": str(args.receipt), "receipt_sha256": sha256_file(args.receipt),
                      "lock_sha256": sha256_file(args.lock_out), "status": receipt["status"]}))


if __name__ == "__main__":
    main()
