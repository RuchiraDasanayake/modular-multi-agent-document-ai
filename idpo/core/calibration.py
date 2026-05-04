from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class CalibrationSample:
    score: float
    label: int


class ConfidenceCalibrator:
    """Field-confidence calibrator supporting Platt scaling and isotonic regression."""

    def __init__(self, method: str = "platt", parameters: Dict[str, float] | None = None) -> None:
        self.method = method
        self.parameters = parameters or {}
        self._platt_a = float(self.parameters.get("a", 1.0))
        self._platt_b = float(self.parameters.get("b", 0.0))
        self._iso_thresholds: List[float] = list(self.parameters.get("thresholds", []))
        self._iso_values: List[float] = list(self.parameters.get("values", []))

    def fit(self, samples: Sequence[CalibrationSample]) -> None:
        if not samples:
            return
        if self.method == "isotonic":
            self._fit_isotonic(samples)
            self.parameters = {"thresholds": self._iso_thresholds, "values": self._iso_values}
            return
        self._fit_platt(samples)
        self.parameters = {"a": self._platt_a, "b": self._platt_b}

    def calibrate(self, score: float) -> float:
        bounded = min(max(score, 1e-6), 1 - 1e-6)
        if self.method == "isotonic" and self._iso_thresholds and self._iso_values:
            return self._predict_isotonic(bounded)
        z = self._platt_a * bounded + self._platt_b
        return 1.0 / (1.0 + math.exp(-z))

    def evaluate(self, samples: Sequence[CalibrationSample], bins: int = 10) -> Dict[str, object]:
        if not samples:
            return {"ece": 0.0, "reliability_curve": [], "count": 0}

        bucket = [[] for _ in range(max(bins, 1))]
        for sample in samples:
            pred = self.calibrate(sample.score)
            idx = min(int(pred * bins), bins - 1)
            bucket[idx].append((pred, sample.label))

        reliability = []
        ece = 0.0
        total = len(samples)
        for idx, rows in enumerate(bucket):
            if not rows:
                continue
            avg_pred = sum(item[0] for item in rows) / len(rows)
            avg_true = sum(item[1] for item in rows) / len(rows)
            gap = abs(avg_pred - avg_true)
            ece += gap * (len(rows) / total)
            reliability.append(
                {
                    "bin": idx,
                    "count": len(rows),
                    "avg_pred": avg_pred,
                    "avg_true": avg_true,
                    "gap": gap,
                }
            )
        return {"ece": ece, "reliability_curve": reliability, "count": total}

    def to_dict(self) -> Dict[str, object]:
        return {"method": self.method, "parameters": self.parameters}

    def save(self, path: str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "ConfidenceCalibrator":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(method=str(payload.get("method", "platt")), parameters=payload.get("parameters", {}))

    def _fit_platt(self, samples: Sequence[CalibrationSample]) -> None:
        a = self._platt_a
        b = self._platt_b
        lr = 0.5
        for _ in range(500):
            grad_a = 0.0
            grad_b = 0.0
            for sample in samples:
                x = min(max(sample.score, 1e-6), 1 - 1e-6)
                y = float(sample.label)
                pred = 1.0 / (1.0 + math.exp(-(a * x + b)))
                grad = pred - y
                grad_a += grad * x
                grad_b += grad
            count = max(len(samples), 1)
            a -= lr * (grad_a / count)
            b -= lr * (grad_b / count)
            lr *= 0.995
        self._platt_a = a
        self._platt_b = b

    def _fit_isotonic(self, samples: Sequence[CalibrationSample]) -> None:
        ordered = sorted((sample.score, float(sample.label)) for sample in samples)
        blocks: List[Dict[str, float]] = []
        for score, label in ordered:
            blocks.append({"sum": label, "count": 1.0, "min_x": score, "max_x": score})
            while len(blocks) >= 2:
                if (blocks[-2]["sum"] / blocks[-2]["count"]) <= (blocks[-1]["sum"] / blocks[-1]["count"]):
                    break
                right = blocks.pop()
                left = blocks.pop()
                merged = {
                    "sum": left["sum"] + right["sum"],
                    "count": left["count"] + right["count"],
                    "min_x": left["min_x"],
                    "max_x": right["max_x"],
                }
                blocks.append(merged)

        thresholds: List[float] = []
        values: List[float] = []
        for block in blocks:
            thresholds.append(block["max_x"])
            values.append(block["sum"] / block["count"])
        self._iso_thresholds = thresholds
        self._iso_values = values

    def _predict_isotonic(self, score: float) -> float:
        for threshold, value in zip(self._iso_thresholds, self._iso_values):
            if score <= threshold:
                return min(max(value, 0.0), 1.0)
        return min(max(self._iso_values[-1], 0.0), 1.0)


def load_calibration_samples(path: str) -> List[CalibrationSample]:
    samples: List[CalibrationSample] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            row = line.strip()
            if not row:
                continue
            payload = json.loads(row)
            samples.extend(_line_to_samples(payload))
    return samples


def _line_to_samples(payload: Dict[str, object]) -> List[CalibrationSample]:
    if "score" in payload and "label" in payload:
        return [CalibrationSample(score=float(payload["score"]), label=int(payload["label"]))]

    fields = payload.get("fields", [])
    samples: List[CalibrationSample] = []
    if isinstance(fields, list):
        for field in fields:
            if not isinstance(field, dict):
                continue
            if "score" in field and "label" in field:
                samples.append(CalibrationSample(score=float(field["score"]), label=int(field["label"])))
                continue
            if "confidence_score" in field and ("correct" in field or "label" in field):
                label = int(field.get("correct", field.get("label", 0)))
                samples.append(CalibrationSample(score=float(field["confidence_score"]), label=label))
    return samples
