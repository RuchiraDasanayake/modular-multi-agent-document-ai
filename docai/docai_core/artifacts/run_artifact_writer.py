from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from docai_core.artifacts.store import ArtifactStore


@dataclass(slots=True)
class RunArtifactWriter:
    artifact_store: ArtifactStore
    generated_by: str
    stub_note: str
    is_stub: bool = True

    def create_job(self, job_id: str) -> None:
        self.artifact_store.create_job(job_id)

    def create_document(self, job_id: str, document_id: str) -> None:
        self.artifact_store.create_document(job_id, document_id)

    def write_job_context(self, job_id: str, job_context: object) -> None:
        self.artifact_store.write_json(self._job_path(job_id, "job_context.json"), job_context)

    def write_document_queue(self, job_id: str, document_queue: object) -> None:
        payload = {
            "job_id": job_id,
            "documents": document_queue,
            "is_stub": self.is_stub,
            "generated_by": self.generated_by,
            "note": self.stub_note,
        }
        self.artifact_store.write_json(self._job_path(job_id, "document_queue.json"), payload)

    def append_run_log(self, job_id: str, event: dict) -> None:
        self.artifact_store.append_jsonl(self._job_path(job_id, "run_log.jsonl"), event)

    def write_document_profile(self, job_id: str, document_id: str, profile: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "document_profile.json"),
            self._with_stub_metadata(profile),
        )

    def write_selected_policy(self, job_id: str, document_id: str, policy: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "selected_policy.json"),
            self._with_stub_metadata(policy),
        )

    def write_run_plan(self, job_id: str, document_id: str, run_plan: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "run_plan.json"),
            self._with_stub_metadata(run_plan),
        )

    def write_ocr_output(self, job_id: str, document_id: str, ocr_output: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "ocr_output.json"),
            self._with_stub_metadata(ocr_output),
        )

    def write_extracted_output(self, job_id: str, document_id: str, extracted_output: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "extracted_output.json"),
            self._with_stub_metadata(extracted_output),
        )

    def write_validation_report(self, job_id: str, document_id: str, validation_report: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "validation_report.json"),
            self._with_stub_metadata(validation_report),
        )

    def write_recovery_report(self, job_id: str, document_id: str, recovery_report: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "recovery_report.json"),
            self._with_stub_metadata(recovery_report),
        )

    def write_final_output(self, job_id: str, document_id: str, final_output: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "final_output.json"),
            self._with_stub_metadata(final_output),
        )

    def write_expected_values(self, job_id: str, document_id: str, expected_values: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "expected_values.json"),
            self._with_stub_metadata(asdict(expected_values)),  # type: ignore[arg-type]
        )

    def write_review_record(self, job_id: str, document_id: str, review_record: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "review_record.json"),
            self._with_stub_metadata(asdict(review_record)),  # type: ignore[arg-type]
        )

    def write_document_metrics(self, job_id: str, document_id: str, document_metrics: object) -> None:
        self.artifact_store.write_json(
            self._doc_path(job_id, document_id, "document_metrics.json"),
            self._with_stub_metadata(asdict(document_metrics)),  # type: ignore[arg-type]
        )

    def write_reviewed_metrics_report(self, job_id: str, reviewed_metrics_report: object) -> None:
        self.artifact_store.write_json(
            self._job_path(job_id, "reviewed_metrics_report.json"),
            self._with_stub_metadata(asdict(reviewed_metrics_report)),  # type: ignore[arg-type]
        )

    def write_metrics_report(self, job_id: str, metrics_report: object) -> None:
        self.artifact_store.write_json(
            self._job_path(job_id, "metrics_report.json"),
            self._with_stub_metadata(metrics_report),
        )

    def write_extracted_data_export(self, job_id: str, export_payload: dict) -> None:
        payload = {
            **export_payload,
            "is_stub": self.is_stub,
            "generated_by": self.generated_by,
            "note": self.stub_note,
        }
        self.artifact_store.write_json(self._job_path(job_id, "extracted_data_export.json"), payload)

    def job_artifact_path(self, job_id: str, filename: str) -> Path:
        return self._job_path(job_id, filename)

    def document_artifact_path(self, job_id: str, document_id: str, filename: str) -> Path:
        return self._doc_path(job_id, document_id, filename)

    def _job_path(self, job_id: str, filename: str) -> Path:
        return self.artifact_store.job_artifact_path(job_id, filename)

    def _doc_path(self, job_id: str, document_id: str, filename: str) -> Path:
        return self.artifact_store.document_artifact_path(job_id, document_id, filename)

    def _with_stub_metadata(self, payload: object) -> dict:
        base = payload.to_dict() if hasattr(payload, "to_dict") and callable(payload.to_dict) else payload
        if not isinstance(base, dict):
            raise TypeError("Expected dict-like payload for stub artifact writing.")
        return {
            **base,
            "is_stub": self.is_stub,
            "generated_by": self.generated_by,
            "note": self.stub_note,
        }
