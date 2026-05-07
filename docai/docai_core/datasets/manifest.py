"""Labeled dataset manifest for benchmark evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DocumentManifestEntry:
    """Single document in a labeled dataset manifest."""

    document_id: str
    file_path: str
    schema_id: str
    expected_values: dict[str, str]
    policy_id: str | None = None


@dataclass(slots=True)
class LabeledDatasetManifest:
    """Manifest of labeled documents for benchmark evaluation."""

    dataset_id: str
    documents: list[DocumentManifestEntry]
