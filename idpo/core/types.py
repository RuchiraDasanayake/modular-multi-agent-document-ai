"""Core domain types used across the IDPO pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

@dataclass(frozen=True)
class Page:
    number: int
    text: str
    raw_text: str | None = None
    image_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Document:
    doc_id: str
    source: str  # "digital" or "scanned" or "synthetic"
    path: str
    pages: list[Page]
    metadata: dict[str, Any] = field(default_factory=dict)
    profile: str | None = None
    quality_score: float | None = None
    complexity_score: float | None = None
    doc_type: str | None = None
    vendor_cluster: str | None = None
    quality_bin: str | None = None
    complexity_bin: str | None = None
    content_profile: str | None = None
    dae_signals: dict[str, Any] = field(default_factory=dict)

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
    layout_cluster_id: str = "unknown"
    route_bin: str = "standard"
    quality_features: dict[str, float] = field(default_factory=dict)
    structural_features: dict[str, float] = field(default_factory=dict)
    signals: dict[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class Entity:
    key: str
    value: str
    confidence: float
    page: int | None = None
    span: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Section:
    name: str
    text: str
    page_start: int | None = None
    page_end: int | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    tokens: int
    page_range: tuple[int, int]
    section: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ValidationIssue:
    field: str
    issue: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class TokenBudget:
    max_tokens: int
    reserved_tokens: int = 0

    @property
    def available(self) -> int:
        return max(self.max_tokens - self.reserved_tokens, 0)

@dataclass
class AgentResult:
    artifacts: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

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
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Answer:
    question: str
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    abstained: bool = False

@dataclass(frozen=True)
class ExtractionPolicy:
    policy_id: str
    name: str
    explicit_entities: list[str] = field(default_factory=list)
    preprocess_force: list[str] = field(default_factory=list)
    preprocess_skip: list[str] = field(default_factory=list)
    model_preference: str | None = None
    matches: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class PolicyDefinition:
    policy_id: str
    name: str
    conditions: dict[str, Any] = field(default_factory=dict)
    actions: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class PlanStep:
    step_id: str
    operator: str
    params: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 0
    budget_units: float = 0.0
    fallback: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    doc_id: str
    policy_id: str
    policy_name: str
    source: str
    steps: list[PlanStep] = field(default_factory=list)
    budgets: dict[str, Any] = field(default_factory=dict)
    retrieval: dict[str, Any] = field(default_factory=dict)
    token_budget: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    created_at: float = 0.0

@dataclass(frozen=True)
class SystemConstraints:
    max_cost_units: float
    max_latency_ms: float
    rate_limit: float | None = None

@dataclass(frozen=True)
class ModelDecision:
    mode: str
    model_name: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

def iter_text(pages: Iterable[Page]) -> str:
    return "\n".join(page.text for page in pages)
