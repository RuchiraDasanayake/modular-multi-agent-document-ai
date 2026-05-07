from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Protocol

from docai_core.contracts.domain import ScalarValue


@dataclass(slots=True)
class ModelPluginConfig:
    plugin_id: str
    provider_name: str
    model_name: str
    enabled: bool = True
    temperature: float = 0.0
    max_tokens: int | None = None
    json_mode: bool = True
    timeout_seconds: int | None = None
    retry_count: int = 0
    settings: dict[str, ScalarValue] = dc_field(default_factory=dict)


@dataclass(slots=True)
class ModelRequest:
    prompt: str
    system_prompt: str | None = None
    context: dict[str, ScalarValue] = dc_field(default_factory=dict)
    expected_format: str = "json"
    schema_hint: dict[str, ScalarValue] = dc_field(default_factory=dict)
    temperature: float | None = None
    max_tokens: int | None = None
    json_mode: bool | None = None
    request_id: str | None = None


@dataclass(slots=True)
class ModelUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None


@dataclass(slots=True)
class ModelResponse:
    text: str
    parsed_json: dict[str, ScalarValue] | None = None
    model_name: str | None = None
    provider_name: str | None = None
    is_stub: bool = False
    success: bool = True
    error_message: str | None = None
    usage: ModelUsage | None = None
    metadata: dict[str, ScalarValue] = dc_field(default_factory=dict)


class ModelPlugin(Protocol):
    plugin_id: str
    provider_name: str
    model_name: str

    def generate(self, request: ModelRequest) -> ModelResponse:
        ...
