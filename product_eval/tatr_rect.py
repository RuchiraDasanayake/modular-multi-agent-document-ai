"""Small, permissive rectangle subset used by pinned TATR postprocessing.

Only the PyMuPDF ``Rect`` operations present in Microsoft's pinned
``inference.py`` and ``postprocess.py`` are implemented. Input validity is
checked by the research adapter before these methods are called.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence


class Rect:
    def __init__(self, values: Sequence[float] | Rect | None = None) -> None:
        if values is None:
            self._box = (0.0, 0.0, 0.0, 0.0)
            self._empty = True
        else:
            coordinates = tuple(float(value) for value in values)
            if len(coordinates) != 4 or not all(math.isfinite(v) for v in coordinates):
                raise ValueError("rectangle requires four finite coordinates")
            self._box = coordinates
            self._empty = coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]

    def __iter__(self) -> Iterator[float]:
        return iter(self._box)

    def __getitem__(self, index: int) -> float:
        return self._box[index]

    def get_area(self) -> float:
        if self._empty:
            return 0.0
        left, top, right, bottom = self._box
        return (right - left) * (bottom - top)

    def intersect(self, other: Sequence[float] | Rect) -> Rect:
        other_rect = Rect(other)
        if self._empty or other_rect._empty:
            self._box = (0.0, 0.0, 0.0, 0.0)
            self._empty = True
            return self
        left = max(self[0], other_rect[0])
        top = max(self[1], other_rect[1])
        right = min(self[2], other_rect[2])
        bottom = min(self[3], other_rect[3])
        self._box = (left, top, right, bottom)
        self._empty = right <= left or bottom <= top
        return self

    def include_rect(self, other: Sequence[float] | Rect) -> Rect:
        other_rect = Rect(other)
        if other_rect._empty:
            return self
        if self._empty:
            self._box = other_rect._box
        else:
            self._box = (
                min(self[0], other_rect[0]),
                min(self[1], other_rect[1]),
                max(self[2], other_rect[2]),
                max(self[3], other_rect[3]),
            )
        self._empty = False
        return self
