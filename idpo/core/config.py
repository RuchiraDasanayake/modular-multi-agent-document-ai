from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class PreprocessingConfig:
    ocr_engine: str = "mock"
    ocr_version: str = "v1"
    ocr_lang: str = "eng"
    ocr_psm: int = 6
    ocr_oem: int = 3
    ocr_dpi: int = 300
    ocr_alt_psm: list[int] = field(default_factory=lambda: [4, 11])
    ocr_passes: int = 2
    deskew: bool = True
    denoise: bool = True
    table_mode: str = "heuristic"
    max_retries: int = 2


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
    allow_generic_kv: bool = True
    heading_max_words: int = 6


@dataclass
class EscalationConfig:
    enabled: bool = True
    max_cost_units: int = 3
    max_escalations_per_run: int = 5
    max_cost_per_doc: float = 3.0
    max_cost_per_minute: float = 12.0
    max_escalations_per_minute: int = 10
    flagship_model: Optional[str] = None
    fallback_mode: str = "simulate"
    estimated_latency_ms_per_field: float = 800.0
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
    max_latency_regression_pct: float = 0.2
    min_validation_pass_delta: float = 0.05


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
    mode: str = "http"
    objective: str = "min_cost"
    timeout_ms: int = 500
    endpoint: Optional[str] = None
    advice_endpoint: str = "/advice"
    log_endpoint: str = "/log"
    direct_import: Optional[str] = None
    policy_override_id: Optional[str] = None
    action_overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CalibrationConfig:
    enabled: bool = False
    method: str = "heuristic"
    version: str = "v1"
    temperature: float = 1.0
    parameters: Dict[str, float] = field(default_factory=dict)
    model_path: Optional[str] = None
    mode: str = "heuristic_only"


@dataclass
class BudgetConfig:
    max_cost_per_doc: float = 6.0
    max_cost_per_minute: float = 50.0
    max_latency_per_doc_ms: float = 10000.0
    max_retries_per_field: int = 2
    max_total_retries_per_doc: int = 8
    escalation_quota_per_doc: int = 2
    escalation_quota_per_minute: int = 10


@dataclass
class AnsweringConfig:
    min_confidence: float = 0.55


@dataclass
class KnowledgeConfig:
    policy_store_path: Optional[str] = None
    default_policy_id: str = "default"


@dataclass
class LLMConfig:
    local_model: str = "local-llm"
    cloud_model: str = "flagship-llm"
    default_mode: str = "local"
    history_signal_key: str = "llm_mode"
    history_mode: Optional[str] = None
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    timeout_s: int = 60
    use_extraction: bool = False
    use_summarization: bool = False
    cloud_provider: str = "openai"
    cloud_timeout_s: int = 60
    cloud_temperature: float = 0.1
    cloud_max_tokens: int = 2000
    allow_cloud_fallback: bool = True
    openai_api_url: str = "https://api.openai.com/v1"
    openai_api_key: str = "sk-PLACEHOLDER"


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
    shadow: ShadowModeConfig = field(default_factory=ShadowModeConfig)
    rollback: RollbackConfig = field(default_factory=RollbackConfig)
    queue: QueueConfig = field(default_factory=QueueConfig)
    ahmn: AHMNConfig = field(default_factory=AHMNConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    answering: AnsweringConfig = field(default_factory=AnsweringConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    seed: int = 13


def config_from_dict(data: Dict[str, Any]) -> PipelineConfig:
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
        if cls is BudgetConfig:
            return BudgetConfig(
                max_cost_per_doc=float(payload.get("max_cost_per_doc", 6.0)),
                max_cost_per_minute=float(payload.get("max_cost_per_minute", 50.0)),
                max_latency_per_doc_ms=float(payload.get("max_latency_per_doc_ms", 10000.0)),
                max_retries_per_field=int(payload.get("max_retries_per_field", 2)),
                max_total_retries_per_doc=int(payload.get("max_total_retries_per_doc", 8)),
                escalation_quota_per_doc=int(payload.get("escalation_quota_per_doc", 2)),
                escalation_quota_per_minute=int(payload.get("escalation_quota_per_minute", 10)),
            )
        return cls(**payload)

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
        shadow=_read(ShadowModeConfig, "shadow"),
        rollback=_read(RollbackConfig, "rollback"),
        queue=_read(QueueConfig, "queue"),
        ahmn=_read(AHMNConfig, "ahmn"),
        calibration=_read(CalibrationConfig, "calibration"),
        budget=_read(BudgetConfig, "budget"),
        answering=_read(AnsweringConfig, "answering"),
        knowledge=_read(KnowledgeConfig, "knowledge"),
        llm=_read(LLMConfig, "llm"),
        seed=data.get("seed", 13),
    )


def load_config(path: Optional[str] = None) -> PipelineConfig:
    if not path:
        return PipelineConfig()

    cfg_path = Path(path)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    return config_from_dict(data)
