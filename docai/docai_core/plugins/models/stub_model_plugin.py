from __future__ import annotations

from dataclasses import dataclass

from docai_core.plugins.models.base import ModelPlugin, ModelRequest, ModelResponse, ModelUsage


@dataclass(slots=True)
class StubModelPlugin(ModelPlugin):
    plugin_id: str = "stub_model_plugin"
    provider_name: str = "Stub Local Model"
    model_name: str = "stub-model"

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text="stub model response",
            parsed_json={"status": "stub", "expected_format": request.expected_format},
            model_name=self.model_name,
            provider_name=self.provider_name,
            is_stub=True,
            success=True,
            usage=ModelUsage(latency_ms=0),
            metadata={"generated_by": self.plugin_id},
        )
