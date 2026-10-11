"""Pipeline configuration dataclasses and JSON loader."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Any

_ENV_FILE_LOADED = False

@dataclass
class PreprocessingConfig:
    ocr_engine: str = "paddle"
    ocr_version: str = "v1"
    ocr_lang: str = "eng"
    ocr_psm: int = 6
    ocr_oem: int = 3
    ocr_dpi: int = 300
    ocr_alt_psm: list[int] = field(default_factory=lambda: [4, 11])
    ocr_passes: int = 2
    ocr_initial_single_pass: bool = False
    ocr_min_confidence: float = 55.0
    ocr_retry_dpi: int = 450
    ocr_retry_alt_psm: list[int] = field(default_factory=lambda: [3, 4, 6, 11, 12])
    ocr_max_reruns_per_page: int = 1
    ocr_rerun_min_score_gain: float = 0.03
    ocr_fast_exit_score: float = 0.82
    ocr_fast_exit_confidence: float = 65.0
    deskew: bool = True
    denoise: bool = True
    table_mode: str = "heuristic"
    max_retries: int = 2
    recovery_confidence: float = 0.6

@dataclass
class ChunkingConfig:
    chunk_size: int = 350
    chunk_overlap: int = 60
    max_chunks: int = 128

@dataclass
class RetrievalConfig:
    dense_k: int = 12
    sparse_k: int = 12
    final_k: int = 12
    mmr_lambda: float = 0.7
    metadata_boost: float = 0.15

@dataclass
class ContextConfig:
    max_tokens: int = 1600
    reserved_tokens: int = 200
    diversity_penalty: float = 0.15

@dataclass
class ValidationConfig:
    min_confidence: float = 0.65
    max_field_errors: int = 3
    rules: list["ValidationRule"] = field(default_factory=list)

@dataclass(frozen=True)
class ExtractionRule:
    key: str
    label: str
    pattern: str

@dataclass(frozen=True)
class ValidationRule:
    field_pattern: str
    value_pattern: str
    severity: str = "medium"
    normalize: str = "strip"

@dataclass
class StructuringConfig:
    extraction_rules: list[ExtractionRule] = field(default_factory=list)
    requested_fields: list[str] = field(default_factory=list)
    field_descriptions: dict[str, str] = field(default_factory=dict)
    allow_generic_kv: bool = True
    heading_max_words: int = 6
    # Canonical expected field schema per doc_type, used by the reward function
    # to avoid circularity (policy-independent evaluation target). Empty dict falls
    # back to policy.explicit_entities for backward compatibility.
    canonical_fields_by_doc_type: dict[str, list[str]] = field(default_factory=lambda: {
        "invoice": [
            "invoice_number", "total_amount", "subtotal", "tax",
            "date", "vendor_name", "customer_name", "due_date",
        ],
        "receipt": [
            "total_amount", "subtotal", "tax", "date",
            "vendor_name", "payment_method",
        ],
        "form_document": [
            "record_id", "document_date", "customer_name", "total_amount",
        ],
        "contract": [
            "title", "date", "parties", "effective_date", "total_value",
        ],
        "agreement": [
            "title", "date", "parties", "effective_date", "total_value",
        ],
        "financial_statement": [
            "total_amount", "subtotal", "tax", "date",
            "invoice_number", "vendor_name",
        ],
        "ledger": [
            "total_amount", "subtotal", "date", "invoice_number",
        ],
        "table_document": [
            "total_amount", "subtotal", "tax", "date",
        ],
        "scanned_document": [
            "title", "author", "date", "summary",
        ],
        "report": [
            "title", "author", "date", "summary",
        ],
        "article": [
            "title", "author", "date", "summary",
        ],
        "letter": [
            "title", "date", "summary",
        ],
        "manual": [
            "title", "date", "summary",
        ],
        "specification": [
            "title", "date", "summary",
        ],
        "mixed_document": [
            "title", "date", "parties", "total_value",
        ],
    })

@dataclass
class EscalationConfig:
    enabled: bool = True
    max_cost_units: int = 3
    max_escalations_per_run: int = 5
    max_cost_per_doc: float = 3.0
    max_cost_per_minute: float = 12.0
    max_escalations_per_minute: int = 10
    flagship_model: str = "flagship-sim"
    fallback_mode: str = "simulate"
    estimated_latency_ms_per_field: float = 900.0
    estimated_cost_per_field: float = 0.5

@dataclass
class RoutingConfig:
    quality_threshold: float = 0.6
    complexity_threshold: float = 0.5
    retry_threshold: float = 0.55
    light_route_threshold: float = 0.35
    heavy_route_threshold: float = 0.7
    table_specialization_threshold: float = 0.2
    form_specialization_threshold: float = 0.2
    image_specialization_threshold: float = 0.5

@dataclass
class PlanConfig:
    default_step_timeout_ms: int = 30000
    default_step_budget_units: float = 1.0
    max_total_budget_units: float = 6.0

@dataclass
class BudgetConfig:
    max_cost_per_doc: float = 7.0
    max_cost_per_minute: float = 60.0
    max_latency_per_doc_ms: float = 12000.0
    max_retries_per_field: int = 2
    max_total_retries_per_doc: int = 8
    escalation_quota_per_doc: int = 2
    escalation_quota_per_minute: int = 10

@dataclass
class ShadowModeConfig:
    enabled: bool = False
    sample_rate: float = 0.0
    candidate_policy_ids: list[str] = field(default_factory=list)
    max_policies_per_doc: int = 1
    comparison_file: str = "comparisons.json"

@dataclass
class RollbackConfig:
    enabled: bool = True
    window_size: int = 25
    latency_p95_ms: float = 2500.0
    validation_failure_rate: float = 0.2
    quality_drop_threshold: float = 0.05
    max_latency_regression_pct: float = 0.25
    min_validation_pass_delta: float = 0.1

@dataclass
class QueueConfig:
    enabled: bool = False
    max_workers: int = 4
    per_partition_concurrency: int = 1
    partition_keys: list[str] = field(default_factory=lambda: ["doc_type", "vendor_cluster"])
    fairness_enabled: bool = True

@dataclass
class AHMNConfig:
    enabled: bool = False
    policy_mode: str = "static"
    mode: str = "mock"
    objective: str = "min_cost"
    timeout_ms: int = 500
    endpoint: str | None = None
    advice_endpoint: str = "/advice"
    log_endpoint: str = "/advice/log"
    direct_import: str | None = None
    policy_override_id: str | None = None
    action_overrides: dict[str, Any] = field(default_factory=dict)

@dataclass
class CalibrationConfig:
    enabled: bool = False
    method: str = "heuristic"
    version: str = "v1"
    temperature: float = 1.0
    parameters: dict[str, float] = field(default_factory=dict)
    model_path: str | None = None
    mode: str = "heuristic_only"

@dataclass
class AnsweringConfig:
    min_confidence: float = 0.55

@dataclass
class KnowledgeConfig:
    policy_store_path: str | None = None
    default_policy_id: str = "default"

@dataclass
class LLMConfig:
    local_model: str = "local-llm"
    cloud_model: str = "flagship-llm"
    flagship_model: str = ""
    default_mode: str = "local"
    history_signal_key: str = "llm_mode"
    history_mode: str | None = None
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    timeout_s: int = 60
    use_extraction: bool = False
    cloud_provider: str = "openai"
    cloud_timeout_s: int = 60
    cloud_temperature: float = 0.0
    cloud_max_tokens: int = 2000
    allow_cloud_fallback: bool = True
    enable_flagship_fallback: bool = True
    flagship_min_missing_fields: int = 1
    max_cloud_fields_per_call: int = 8
    prompt_max_chars: int = 18000
    context_window_lines: int = 1
    prefer_targeted_context: bool = True
    strict_json_output: bool = True
    cloud_retry_without_json_mode: bool = True
    # Local (Ollama) generation controls.
    # temperature=0 + format=json => deterministic structured output on phi3/llama3.
    local_temperature: float = 0.0
    local_format_json: bool = True
    local_num_predict: int = 4096
    local_top_p: float = 0.8
    local_top_k: int = 20
    local_num_ctx: int = 8192
    # Persist raw prompt and raw model response in the document artifact for
    # monitoring and re-audit. Turn off only if payloads contain sensitive data
    # that must never land on disk.
    persist_raw_llm_io: bool = True
    refine_field_descriptions: bool = True
    description_refinement_model: str = ""
    description_refinement_use_cloud: bool = False
    description_refinement_max_tokens: int = 400
    description_refinement_temperature: float = 0.0
    description_refinement_max_fields: int = 24
    openai_api_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""

@dataclass
class PipelineConfig:
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    structuring: StructuringConfig = field(default_factory=StructuringConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    shadow: ShadowModeConfig = field(default_factory=ShadowModeConfig)
    rollback: RollbackConfig = field(default_factory=RollbackConfig)
    queue: QueueConfig = field(default_factory=QueueConfig)
    ahmn: AHMNConfig = field(default_factory=AHMNConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    answering: AnsweringConfig = field(default_factory=AnsweringConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    seed: int = 13

def config_from_dict(data: dict[str, Any]) -> PipelineConfig:
    def _filter_known_keys(cls: Any, payload: dict[str, Any]) -> dict[str, Any]:
        known = {item.name for item in dataclass_fields(cls)}
        return {key: value for key, value in payload.items() if key in known}

    def _read(cls, key: str) -> Any:
        payload = data.get(key, {})
        if not payload:
            return cls()
        if cls is ValidationConfig:
            rules = []
            for item in payload.get("rules", []):
                rules.append(ValidationRule(**item))
            return ValidationConfig(
                min_confidence=payload.get("min_confidence", 0.65),
                max_field_errors=payload.get("max_field_errors", 3),
                rules=rules,
            )
        if cls is StructuringConfig:
            rules = []
            for item in payload.get("extraction_rules", []):
                rules.append(ExtractionRule(**item))
            return StructuringConfig(
                extraction_rules=rules,
                requested_fields=[
                    str(item).strip()
                    for item in payload.get("requested_fields", [])
                    if str(item).strip()
                ],
                field_descriptions={
                    str(key).strip(): str(value).strip()
                    for key, value in payload.get("field_descriptions", {}).items()
                    if str(key).strip()
                }
                if isinstance(payload.get("field_descriptions"), dict)
                else {},
                allow_generic_kv=payload.get("allow_generic_kv", True),
                heading_max_words=payload.get("heading_max_words", 6),
            )
        if cls is CalibrationConfig:
            return CalibrationConfig(
                enabled=payload.get("enabled", False),
                method=payload.get("method", "heuristic"),
                version=payload.get("version", "v1"),
                temperature=payload.get("temperature", 1.0),
                parameters=payload.get("parameters", {}),
                model_path=payload.get("model_path"),
                mode=payload.get("mode", "heuristic_only"),
            )
        return cls(**_filter_known_keys(cls, payload))

    return PipelineConfig(
        preprocessing=_read(PreprocessingConfig, "preprocessing"),
        chunking=_read(ChunkingConfig, "chunking"),
        retrieval=_read(RetrievalConfig, "retrieval"),
        context=_read(ContextConfig, "context"),
        validation=_read(ValidationConfig, "validation"),
        structuring=_read(StructuringConfig, "structuring"),
        escalation=_read(EscalationConfig, "escalation"),
        routing=_read(RoutingConfig, "routing"),
        plan=_read(PlanConfig, "plan"),
        budget=_read(BudgetConfig, "budget"),
        shadow=_read(ShadowModeConfig, "shadow"),
        rollback=_read(RollbackConfig, "rollback"),
        queue=_read(QueueConfig, "queue"),
        ahmn=_read(AHMNConfig, "ahmn"),
        calibration=_read(CalibrationConfig, "calibration"),
        answering=_read(AnsweringConfig, "answering"),
        knowledge=_read(KnowledgeConfig, "knowledge"),
        llm=_read(LLMConfig, "llm"),
        seed=data.get("seed", 13),
    )

def _resolve_env_vars(data: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(data, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        return re.sub(r"\$\{([^}]+)\}", _replace, data)
    if isinstance(data, dict):
        return {key: _resolve_env_vars(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_resolve_env_vars(item) for item in data]
    return data

def _load_dotenv_files(search_roots: list[Path]) -> None:
    """Best-effort .env loader for local runs.

    Loads variables from the first existing .env file found in ``search_roots``.
    Existing process environment values are preserved.
    """
    global _ENV_FILE_LOADED
    if _ENV_FILE_LOADED:
        return

    candidate_files: list[Path] = []
    for root in search_roots:
        candidate_files.append(root / ".env")

    for env_path in candidate_files:
        if not env_path.exists() or not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                if key not in os.environ:
                    os.environ[key] = value
            _ENV_FILE_LOADED = True
            return
        except Exception:
            # Never fail config loading because of .env parse issues.
            continue

def load_config(path: str | None = None) -> PipelineConfig:
    cwd_root = Path.cwd()
    if path:
        cfg_path = Path(path)
        _load_dotenv_files([cfg_path.parent.parent.resolve(), cfg_path.parent.resolve(), cwd_root])
    else:
        _load_dotenv_files([cwd_root])

    if not path:
        return PipelineConfig()

    cfg_path = Path(path)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data = _resolve_env_vars(data)
    return config_from_dict(data)
