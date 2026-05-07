from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import Document, Job, QueuedDocument


@dataclass(slots=True)
class DocumentQueueBuilder:
    def build_queue(self, job: Job, documents: list[Document]) -> list[QueuedDocument]:
        review_status = "required" if job.run_type == "training" else "optional"
        queued: list[QueuedDocument] = []
        for document in documents:
            queued.append(
                QueuedDocument(
                    document_id=document.document_id,
                    job_id=job.job_id,
                    filename=document.original_filename,
                    file_path=document.file_path,
                    queue_status="queued",
                    profile_status="pending",
                    strategy_status="pending",
                    processing_status="not_started",
                    review_status=review_status,
                    created_at=job.created_at,
                    updated_at=job.created_at,
                )
            )
        return queued
