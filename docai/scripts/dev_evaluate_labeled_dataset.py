#!/usr/bin/env python3
"""Labeled dataset evaluation harness for benchmark testing.

IMPORTANT: This harness is for test-only and real-dataset evaluation.

Synthetic Tests (automated pytest fixtures):
- Creates minimal synthetic .txt files with KV pairs at test runtime.
- Expected values hardcoded in test code.
- Purpose: validate harness logic, NOT claim benchmark performance.

Real-Dataset Evaluation (user-provided manifest):
- User provides manifest.json with paths to their documents and expected values.
- Runs extraction on real documents (not synthetic fixtures).
- Computes metrics by comparing final_output.json vs. expected values.
- Produces evaluation summary.

Does not modify policies, create human review records, mutate expected values
from extraction output, or implement any learning functionality.

NOTE: Dataset labels are expected values for metric computation, NOT human
review judgments. No production runtime should depend on this harness.

Usage:
  python scripts/dev_evaluate_labeled_dataset.py manifest.json output_dir
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docai_core.application.job_run_service import JobRunRequest, JobRunService
from docai_core.application.review_evaluation_service import (
    ReviewEvaluationAppRequest,
    ReviewEvaluationApplicationService,
)
from docai_core.artifacts.run_artifact_writer import RunArtifactWriter
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    FieldOutput,
    FinalOutput,
    Job,
    Project,
    RecoveryReport,
    ValidationReport,
)
from docai_core.datasets.manifest import DocumentManifestEntry, LabeledDatasetManifest
from docai_core.orchestration.pipeline_factory import build_stub_pipeline
from docai_core.review.expected_values import ExpectedFieldValue, ExpectedValues
from docai_core.schemas import load_extraction_schema


@dataclass(slots=True)
class EvaluationResult:
    """Summary of dataset evaluation."""

    dataset_id: str
    document_count: int
    evaluated_count: int
    schema_ids: list[str]
    field_accuracies: dict[str, float | None]
    overall_accuracies: list[float | None]
    errors: list[str]


def _load_manifest(manifest_path: Path) -> LabeledDatasetManifest:
    """Load and parse manifest JSON."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return LabeledDatasetManifest(
        dataset_id=data["dataset_id"],
        documents=[
            DocumentManifestEntry(
                document_id=d["document_id"],
                file_path=d["file_path"],
                schema_id=d["schema_id"],
                expected_values=d["expected_values"],
                policy_id=d.get("policy_id"),
            )
            for d in data["documents"]
        ],
    )


def _validate_manifest(manifest: LabeledDatasetManifest) -> list[str]:
    """Validate manifest entries. Return list of error strings."""
    errors: list[str] = []

    for entry in manifest.documents:
        # Validate file exists
        file_path = Path(entry.file_path)
        if not file_path.exists():
            errors.append(f"Doc {entry.document_id}: file not found: {entry.file_path}")

        # Validate schema exists
        schema = None
        try:
            schema = load_extraction_schema(entry.schema_id)
        except ValueError as e:
            errors.append(f"Doc {entry.document_id}: {str(e)}")

        # Validate expected field names exist in schema (if schema loaded)
        if schema is not None:
            schema_field_names = {f.name for f in schema.fields}
            for field_name in entry.expected_values.keys():
                if field_name not in schema_field_names:
                    errors.append(
                        f"Doc {entry.document_id}: expected field '{field_name}' "
                        f"not in schema {entry.schema_id}"
                    )

    return errors


def _run_document_extraction(
    entry: DocumentManifestEntry, artifact_store: ArtifactStore, pipeline_config=None
) -> tuple[str, FinalOutput]:
    """Run extraction on one document. Return (job_id, FinalOutput)."""
    schema = load_extraction_schema(entry.schema_id)
    now = datetime.now(timezone.utc)
    job_id = f"dataset-{entry.document_id}"

    file_path = Path(entry.file_path)
    project = Project(
        project_id="dataset_eval", name="Dataset Evaluation",
        description=None, created_at=now, updated_at=now,
    )
    job = Job(
        job_id=job_id, project_id="dataset_eval", schema_id=entry.schema_id,
        name=f"eval-{entry.document_id}", run_type="training",
        status="queued", created_at=now,
    )
    documents = [
        Document(
            document_id=entry.document_id, job_id=job_id,
            original_filename=file_path.name, file_path=str(file_path),
            status="processing", uploaded_at=now,
            profile=DocumentProfile(document_id=entry.document_id),
        )
    ]

    cfg = pipeline_config or build_stub_pipeline()
    JobRunService(artifact_store=artifact_store, pipeline_config=cfg).run_job(
        JobRunRequest(project=project, schema=schema, job=job, documents=documents)
    )

    # Read final_output from artifacts
    final_output_data = artifact_store.read_json(
        artifact_store.document_artifact_path(job_id, entry.document_id, "final_output.json")
    )
    final_output = FinalOutput(
        document_id=final_output_data["document_id"],
        schema_id=final_output_data["schema_id"],
        policy_id=final_output_data["policy_id"],
        fields=[
            FieldOutput(
                field_name=f["field_name"],
                value=f.get("value"),
                confidence=f.get("confidence"),
                extraction_method=f.get("extraction_method"),
                validation_status=f.get("validation_status", "needs_review"),
            )
            for f in final_output_data.get("fields", [])
        ],
        tables=[],
        validation_report=ValidationReport(document_id=entry.document_id, pass_status=True),
        recovery_report=RecoveryReport(document_id=entry.document_id),
        quality_summary=final_output_data.get("quality_summary"),
    )

    return job_id, final_output


def evaluate_dataset(
    manifest: LabeledDatasetManifest,
    artifact_store: ArtifactStore,
    pipeline_config=None,
) -> EvaluationResult:
    """Evaluate all documents in manifest. Return summary result."""
    errors = _validate_manifest(manifest)
    if errors:
        return EvaluationResult(
            dataset_id=manifest.dataset_id,
            document_count=len(manifest.documents),
            evaluated_count=0,
            schema_ids=[],
            field_accuracies={},
            overall_accuracies=[],
            errors=errors,
        )

    result_by_job: dict[str, tuple[str, FinalOutput]] = {}
    expected_values_by_doc: dict[str, ExpectedValues] = {}
    schema_ids: set[str] = set()
    all_errors: list[str] = []

    for entry in manifest.documents:
        try:
            job_id, final_output = _run_document_extraction(entry, artifact_store, pipeline_config)
            result_by_job[entry.document_id] = (job_id, final_output)
            schema_ids.add(entry.schema_id)

            ev = ExpectedValues(
                document_id=entry.document_id,
                schema_id=entry.schema_id,
                fields=[
                    ExpectedFieldValue(field_name=k, expected_value=v)
                    for k, v in entry.expected_values.items()
                ],
                source="dataset_label",
                is_human_review=False,
            )
            expected_values_by_doc[entry.document_id] = ev

            # Write expected_values.json to artifacts
            writer = RunArtifactWriter(
                artifact_store=artifact_store,
                generated_by="labeled_dataset_evaluation",
                stub_note="Labeled dataset evaluation harness",
            )
            writer.write_expected_values(job_id, entry.document_id, ev)
        except Exception as e:
            all_errors.append(f"Doc {entry.document_id}: {str(e)}")

    # Evaluate metrics for all documents that ran
    field_accuracies: dict[str, float | None] = {}
    overall_accuracies: list[float | None] = []

    for doc_id, (job_id, final_output) in result_by_job.items():
        try:
            eval_result = ReviewEvaluationApplicationService(artifact_store=artifact_store).evaluate_reviewed_outputs(
                ReviewEvaluationAppRequest(
                    job_id=job_id,
                    final_outputs=[final_output],
                    expected_values_by_document_id={doc_id: expected_values_by_doc[doc_id]},
                )
            )
            # Read document_metrics to get field_accuracy and overall_accuracy
            metrics_data = artifact_store.read_json(
                artifact_store.document_artifact_path(job_id, doc_id, "document_metrics.json")
            )
            field_accuracies[doc_id] = metrics_data.get("field_accuracy")
            overall_accuracies.append(metrics_data.get("overall_accuracy"))
        except Exception as e:
            all_errors.append(f"Metrics {doc_id}: {str(e)}")

    return EvaluationResult(
        dataset_id=manifest.dataset_id,
        document_count=len(manifest.documents),
        evaluated_count=len(result_by_job),
        schema_ids=sorted(schema_ids),
        field_accuracies=field_accuracies,
        overall_accuracies=overall_accuracies,
        errors=all_errors,
    )


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/dev_evaluate_labeled_dataset.py manifest.json output_dir")
        sys.exit(1)

    manifest_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not manifest_path.exists():
        print(f"Error: manifest not found: {manifest_path}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load and evaluate
    manifest = _load_manifest(manifest_path)
    artifact_store = ArtifactStore(output_dir / "artifacts")
    result = evaluate_dataset(manifest, artifact_store)

    # Write summary JSON
    summary_path = output_dir / "evaluation_summary.json"
    summary_data: dict[str, Any] = {
        "dataset_id": result.dataset_id,
        "document_count": result.document_count,
        "evaluated_count": result.evaluated_count,
        "schema_ids": result.schema_ids,
        "field_accuracies": result.field_accuracies,
        "mean_overall_accuracy": (
            sum(a for a in result.overall_accuracies if a is not None) / len([a for a in result.overall_accuracies if a is not None])
            if any(a is not None for a in result.overall_accuracies)
            else None
        ),
        "errors": result.errors,
    }
    summary_path.write_text(json.dumps(summary_data, indent=2, default=str), encoding="utf-8")
    print(f"Summary written to {summary_path}")

    # Write CSV summary
    csv_path = output_dir / "evaluation_summary.csv"
    csv_lines = [
        "document_id,schema_id,field_accuracy,status",
    ]
    for doc_id, accuracy in result.field_accuracies.items():
        status = "success" if accuracy is not None else "error"
        csv_lines.append(f"{doc_id},{doc_id.split('-')[0]},{accuracy},{status}")
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    print(f"CSV written to {csv_path}")

    if result.errors:
        print(f"\nWarnings/errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")

    print(f"\nEvaluation complete: {result.evaluated_count}/{result.document_count} documents evaluated")


if __name__ == "__main__":
    main()
