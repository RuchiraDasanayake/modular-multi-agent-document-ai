from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import Document, ExtractionSchema, RunPlan, SelectedPolicy


@dataclass(slots=True)
class RunPlanBuilder:
    def build_run_plan(
        self,
        schema: ExtractionSchema,
        document: Document,
        selected_policy: SelectedPolicy,
    ) -> RunPlan:
        filename = document.original_filename.lower()
        preprocessing = ["denoise", "deskew"] if ("scan" in filename or "noisy" in filename) else ["normalize"]
        return RunPlan(
            plan_id=f"{document.document_id}_plan",
            document_id=document.document_id,
            schema_id=schema.schema_id,
            policy_id=selected_policy.policy_id,
            preprocessing_steps=preprocessing,
            ocr_config={"engine": "fake_ocr", "mode": "stub"},
            parser_config={"enabled": False},
            model_config={"provider": "fake", "model": "fake-local"},
            fields_to_extract=[f.name for f in schema.fields],
            tables_to_extract=[t.name for t in schema.tables],
            validation_rules=["required_field_check"],
            recovery_rules=["no_recovery_for_fake_pipeline"],
        )
