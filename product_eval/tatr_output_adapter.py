"""Source-free DETR output shape adapter; no table-cell reconstruction."""

from __future__ import annotations

import math
from collections.abc import Sequence

CLASS_LABELS = {
    "detection": ("table", "table rotated"),
    "structure": (
        "table", "table column", "table row", "table column header",
        "table projected row header", "table spanning cell",
    ),
}


def adapt_detr_outputs(
    logits: Sequence[Sequence[float]],
    normalized_boxes: Sequence[Sequence[float]],
    image_size: tuple[int, int],
    *,
    model_kind: str,
) -> list[dict[str, object]]:
    """Map raw DETR queries to official class names and original-image boxes.

    Keep every query, including the no-object class and boxes outside the
    image. The later crop and cell stages must make their own explicit choice.
    """
    try:
        labels = CLASS_LABELS[model_kind]
    except KeyError as exc:
        raise ValueError("unsupported Table Transformer model kind") from exc
    width, height = image_size
    if width <= 0 or height <= 0 or len(logits) != len(normalized_boxes):
        raise ValueError("invalid image size or mismatched DETR query arrays")
    adapted: list[dict[str, object]] = []
    for query_index, (scores, box) in enumerate(zip(logits, normalized_boxes, strict=True)):
        if len(scores) != len(labels) + 1 or len(box) != 4:
            raise ValueError("DETR query shape differs from pinned class map")
        if not all(math.isfinite(value) for value in (*scores, *box)):
            raise ValueError("nonfinite DETR output")
        cx, cy, box_width, box_height = box
        if box_width <= 0 or box_height <= 0:
            raise ValueError("DETR box has no area")
        maximum = max(scores)
        exponentials = [math.exp(score - maximum) for score in scores]
        probabilities = [value / sum(exponentials) for value in exponentials]
        class_index = max(range(len(scores)), key=probabilities.__getitem__)
        pixel_box = (
            (cx - box_width / 2) * width,
            (cy - box_height / 2) * height,
            (cx + box_width / 2) * width,
            (cy + box_height / 2) * height,
        )
        adapted.append({
            "query_index": query_index,
            "label": labels[class_index] if class_index < len(labels) else "no object",
            "class_index": class_index,
            "score": probabilities[class_index],
            "bbox": pixel_box,
            "normalized_cxcywh": tuple(box),
            "inside_image": 0 <= pixel_box[0] < pixel_box[2] <= width
            and 0 <= pixel_box[1] < pixel_box[3] <= height,
            "above_frozen_threshold": class_index < len(labels) and probabilities[class_index] >= 0.5,
        })
    return adapted
