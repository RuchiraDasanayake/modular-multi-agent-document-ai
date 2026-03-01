from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    raw_text: Optional[str] = None
    image_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Document:
    doc_id: str
    source: str  # "digital" or "scanned" or "synthetic"
    path: str
    pages: List[Page]
    metadata: Dict[str, Any] = field(default_factory=dict)
    profile: Optional[str] = None
    quality_score: Optional[float] = None
    complexity_score: Optional[float] = None
    doc_type: Optional[str] = None
    vendor_cluster: Optional[str] = None
    quality_bin: Optional[str] = None
    complexity_bin: Optional[str] = None
    content_profile: Optional[str] = None
    dae_signals: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DAEOutput:
    doc_id: str
    doc_type: str
    vendor_cluster: str
    quality_bin: str
    complexity_bin: str
    content_profile: str
    quality_score: float
    complexity_score: float
    layout_cluster_id: str = "layout:unknown"
    route_bin: str = "standard"
    quality_features: Dict[str, float] = field(default_factory=dict)
    structural_features: Dict[str, float] = field(default_factory=dict)
    analysis_confidence: float = 0.5
    confidence_type: str = "heuristic"
    signals: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Entity:
    key: str
    value: str
    confidence: float
    confidence_type: str = "heuristic"
    extraction_method: str = "rule_based"
    page: Optional[int] = None
    span: Optional[tuple[int, int]] = None
    bbox: Optional[tuple[int, int, int, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FieldExtraction:
    key: str
    value: str
    evidence_span: Optional[tuple[int, int]] = None
    evidence_bbox: Optional[tuple[int, int, int, int]] = None
    confidence_score: float = 0.0
    confidence_type: str = "heuristic"
    extraction_method: str = "rule_based"
    discovered: bool = False
    page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    name: str
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    tokens: int
    page_range: tuple[int, int]
    section: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    issue: str
    severity: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenBudget:
    max_tokens: int
    reserved_tokens: int = 0

    @property
    def available(self) -> int:
        return max(self.max_tokens - self.reserved_tokens, 0)


@dataclass
class AgentResult:
    artifacts: Dict[str, Any] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)

    def merge(self, other: "AgentResult") -> "AgentResult":
        merged = AgentResult(
            artifacts={**self.artifacts, **other.artifacts},
            messages=[*self.messages, *other.messages],
        )
        return merged


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float
    dense_score: float
    sparse_score: float
    metadata_score: float
    rank: int


@dataclass(frozen=True)
class StageSignal:
    stage: str
    confidence: float
    uncertainty: float
    failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    question: str
    answer: str
    citations: List[Dict[str, Any]]
    confidence: float
    abstained: bool = False


@dataclass(frozen=True)
class ExtractionPolicy:
    policy_id: str
    name: str
    explicit_entities: List[str] = field(default_factory=list)
    preprocess_force: List[str] = field(default_factory=list)
    preprocess_skip: List[str] = field(default_factory=list)
    model_preference: Optional[str] = None
    matches: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDefinition:
    policy_id: str
    name: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    actions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    operator: str
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 0
    budget_units: float = 0.0
    fallback: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    doc_id: str
    policy_id: str
    policy_name: str
    source: str
    steps: List[PlanStep] = field(default_factory=list)
    budgets: Dict[str, Any] = field(default_factory=dict)
    retrieval: Dict[str, Any] = field(default_factory=dict)
    token_budget: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    created_at: float = 0.0


@dataclass(frozen=True)
class SystemConstraints:
    max_cost_units: float
    max_latency_ms: float
    rate_limit: Optional[float] = None


@dataclass(frozen=True)
class ModelDecision:
    mode: str
    model_name: str
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def iter_text(pages: Iterable[Page]) -> str:
    return "\n".join(page.text for page in pages)
