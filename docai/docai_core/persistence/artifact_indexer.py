"""Artifact indexing bridge: read execution artifacts and index into SQLite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from docai_core.persistence.sqlite_store import SQLiteStore


class ArtifactIndexer:
    """Index execution artifacts into SQLite for analysis and review."""

    def __init__(self, store: SQLiteStore):
        """Initialize indexer with SQLiteStore."""
        self.store = store

    def index_run_artifacts(
        self, run_id: str, artifact_root: str | Path, document_id: str | None = None
    ) -> dict[str, Any]:
        """Index artifacts for a run from disk into SQLite.

        Args:
            run_id: Run ID to index artifacts for
            artifact_root: Root directory containing job artifacts
            document_id: Optional document ID to index artifacts for specific document only

        Returns:
            dict with keys:
            - artifacts_indexed: count of run_artifacts indexed
            - metrics_indexed: whether document_metrics were indexed
            - warnings: list of warning messages
            - errors: list of error messages
        """
        result = {
            "artifacts_indexed": 0,
            "metrics_indexed": False,
            "warnings": [],
            "errors": [],
        }

        artifact_root = Path(artifact_root)

        # Verify run exists
        try:
            run = self.store.get_run(run_id)
        except ValueError:
            result["errors"].append(f"Run not found: {run_id}")
            return result

        # Verify artifact root exists
        if not artifact_root.exists():
            result["errors"].append(f"Artifact root does not exist: {artifact_root}")
            return result

        # Determine which documents to index
        documents_to_index = []
        if document_id:
            documents_to_index = [document_id]
        else:
            # Find all documents for this run
            try:
                run_docs = self.store.list_run_documents(run_id)
                documents_to_index = [rd["document_id"] for rd in run_docs]
            except Exception as e:
                result["errors"].append(f"Failed to list run documents: {str(e)}")
                return result

        # Index artifacts
        result["artifacts_indexed"] = self._index_artifacts(
            run_id, artifact_root, documents_to_index, result["warnings"], result["errors"]
        )

        # Index metrics if available
        result["metrics_indexed"] = self._index_metrics(
            run_id, artifact_root, documents_to_index, result["warnings"], result["errors"]
        )

        return result

    def _index_artifacts(
        self, run_id: str, artifact_root: Path, documents: list[str],
        warnings: list[str], errors: list[str],
    ) -> int:
        """Index run and document artifacts."""
        count = 0

        # Map of artifact filename to (artifact_type, is_document_level)
        artifact_types = {
            "final_output.json": ("final_output", True),
            "validation_report.json": ("validation_report", True),
            "selected_policy.json": ("selected_policy", False),
            "expected_values.json": ("expected_values", True),
            "review_record.json": ("review_record", True),
            "document_metrics.json": ("document_metrics", True),
            "ocr_output.json": ("ocr_output", True),
            "extracted_output.json": ("extracted_output", True),
            "run_plan.json": ("run_plan", False),
            "recovery_report.json": ("recovery_report", True),
        }

        # Index run-level artifacts
        for filename, (artifact_type, _) in artifact_types.items():
            if artifact_type == "run_plan" or artifact_type == "selected_policy":
                artifact_path = artifact_root / filename
                if artifact_path.exists():
                    try:
                        payload = self._read_json_file(artifact_path)
                        if not self._artifact_exists_with_hash(run_id, None, artifact_type, payload):
                            self.store.add_run_artifact(
                                run_id=run_id,
                                document_id=None,
                                artifact_type=artifact_type,
                                schema_version="v1",
                                payload=payload,
                            )
                            count += 1
                    except Exception as e:
                        errors.append(f"Failed to index {filename}: {str(e)}")

        # Index document-level artifacts
        for doc_id in documents:
            doc_path = artifact_root / "documents" / doc_id
            if not doc_path.exists():
                continue

            for filename, (artifact_type, is_doc_level) in artifact_types.items():
                if not is_doc_level:
                    continue

                artifact_path = doc_path / filename
                if artifact_path.exists():
                    try:
                        payload = self._read_json_file(artifact_path)
                        if not self._artifact_exists_with_hash(run_id, doc_id, artifact_type, payload):
                            self.store.add_run_artifact(
                                run_id=run_id,
                                document_id=doc_id,
                                artifact_type=artifact_type,
                                schema_version="v1",
                                payload=payload,
                            )
                            count += 1
                    except Exception as e:
                        errors.append(f"Failed to index {filename} for {doc_id}: {str(e)}")

        return count

    def _read_json_file(self, path: Path) -> dict[str, Any]:
        """Read JSON from file."""
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _artifact_exists_with_hash(
        self, run_id: str, document_id: str | None, artifact_type: str, payload: dict[str, Any]
    ) -> bool:
        """Check if artifact with same hash already exists."""
        payload_hash = self._hash_json(payload)
        try:
            artifacts = self.store.list_run_artifacts(run_id, document_id, artifact_type)
            for art in artifacts:
                if art.get("payload_hash") == payload_hash:
                    return True
        except Exception:
            pass
        return False

    def _hash_json(self, obj: dict[str, Any]) -> str:
        """Compute JSON hash."""
        json_str = json.dumps(obj, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _index_metrics(
        self, run_id: str, artifact_root: Path, documents: list[str],
        warnings: list[str], errors: list[str],
    ) -> bool:
        """Index document metrics if available."""
        indexed = False

        for doc_id in documents:
            doc_path = artifact_root / "documents" / doc_id
            metrics_path = doc_path / "document_metrics.json"

            if not metrics_path.exists():
                continue

            try:
                metrics = self._read_json_file(metrics_path)
                expected_values_path = doc_path / "expected_values.json"

                # Get provenance from expected_values if available
                evidence_source = "unknown"
                is_human_review = 0
                if expected_values_path.exists():
                    try:
                        expected_values = self._read_json_file(expected_values_path)
                        evidence_source = expected_values.get("source", "unknown")
                        is_human_review = 1 if expected_values.get("is_human_review", False) else 0
                    except Exception as e:
                        warnings.append(
                            f"Could not read expected_values for {doc_id}, using default provenance: {str(e)}"
                        )

                # Get run context
                run = self.store.get_run(run_id)

                # Add metrics
                self.store.add_document_metrics_index(
                    project_id=run.project_id,
                    job_id=run.job_id,
                    run_id=run_id,
                    document_id=doc_id,
                    schema_id=run.schema_id,
                    evidence_source=evidence_source,
                    is_human_review=is_human_review,
                    policy_id=run.policy_id,
                    field_precision=metrics.get("field_precision"),
                    field_recall=metrics.get("field_recall"),
                    field_f1=metrics.get("field_f1"),
                    accuracy=metrics.get("accuracy"),
                    missing_rate=metrics.get("missing_rate"),
                    correction_rate=metrics.get("correction_rate"),
                )
                indexed = True
            except Exception as e:
                errors.append(f"Failed to index metrics for {doc_id}: {str(e)}")

        return indexed
