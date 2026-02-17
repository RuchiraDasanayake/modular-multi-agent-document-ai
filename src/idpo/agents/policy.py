from __future__ import annotations

import time
from typing import Optional

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.policy_store import PolicyStore
from idpo.core.types import AgentResult, DAEOutput, Document, ModelDecision, PolicyDefinition, StageSignal


class PolicyRetrievalAgent(Agent):
    name = "policy_retrieval"
    version = "v1"
    input_contract = {"document": "Document", "dae_output": "DAEOutput|None"}
    output_contract = {"policy": "PolicyDefinition", "reason": "str", "signal": "StageSignal"}

    def __init__(self) -> None:
        self._store: Optional[PolicyStore] = None
        self._store_path: Optional[str] = None
        self._default_policy_id: Optional[str] = None

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        dae_output: Optional[DAEOutput] = payload.get("dae_output")
        store = self._get_store(ctx)
        if dae_output is None:
            dae_output = DAEOutput(
                doc_id=doc.doc_id,
                doc_type=doc.doc_type or doc.metadata.get("doc_type", "unknown"),
                vendor_cluster=doc.vendor_cluster or doc.metadata.get("vendor_cluster", "unknown"),
                quality_bin=doc.quality_bin or doc.metadata.get("quality_bin", "B"),
                complexity_bin=doc.complexity_bin or doc.metadata.get("complexity_bin", "2"),
                content_profile=doc.content_profile or doc.profile or "text-heavy",
                quality_score=doc.quality_score or 0.0,
                complexity_score=doc.complexity_score or 0.0,
                signals=doc.dae_signals or {},
            )
        policy, reason = store.select_policy(dae_output, doc)
        doc.metadata["policy_id"] = policy.policy_id
        doc.metadata["policy_name"] = policy.name
        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_policy.json",
            store.to_payload(policy, reason),
            kind="policy",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7,
            uncertainty=0.3,
            metadata={"policy_id": policy.policy_id, "selection_reason": reason},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"policy_id": policy.policy_id, "artifact_id": artifact.artifact_id},
            parameters={"default_policy": store.default_policy_id},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"policy": policy, "policy_reason": reason, "policy_artifact": artifact, "signal": signal})

    def _get_store(self, ctx: AgentContext) -> PolicyStore:
        path = ctx.config.knowledge.policy_store_path
        default_policy_id = ctx.config.knowledge.default_policy_id
        if self._store and self._store_path == path and self._default_policy_id == default_policy_id:
            return self._store
        self._store = PolicyStore(path, default_policy_id=default_policy_id)
        self._store_path = path
        self._default_policy_id = default_policy_id
        return self._store


class ModelSelectionAgent(Agent):
    name = "model_selection"
    version = "v1"
    input_contract = {"document": "Document", "policy": "PolicyDefinition|None"}
    output_contract = {"decision": "ModelDecision", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        policy: Optional[PolicyDefinition] = payload.get("policy")
        history_mode = doc.metadata.get(ctx.config.llm.history_signal_key) or ctx.config.llm.history_mode
        mode = self._select_mode(history_mode, policy, ctx)
        model_name = ctx.config.llm.cloud_model if mode == "cloud" else ctx.config.llm.local_model
        reason = self._reason(history_mode, policy)
        decision = ModelDecision(
            mode=mode,
            model_name=model_name,
            reason=reason,
            metadata={"history_mode": history_mode, "policy_preference": getattr(policy, "model_preference", None)},
        )
        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_model_selection.json",
            decision.__dict__,
            kind="model_selection",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7,
            uncertainty=0.3,
            metadata={"mode": mode, "model_name": model_name, "reason": reason},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"mode": mode, "model_name": model_name, "artifact_id": artifact.artifact_id},
            parameters={"default_mode": ctx.config.llm.default_mode},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"model_decision": decision, "model_artifact": artifact, "signal": signal})

    def _select_mode(self, history_mode: Optional[str], policy: Optional[PolicyDefinition], ctx: AgentContext) -> str:
        if history_mode in {"local", "cloud"}:
            return history_mode
        model_tier = None
        if policy:
            model_tier = policy.actions.get("extraction", {}).get("model_tier")
        if model_tier in {"local", "cloud"}:
            return model_tier
        return ctx.config.llm.default_mode if ctx.config.llm.default_mode in {"local", "cloud"} else "local"

    def _reason(self, history_mode: Optional[str], policy: Optional[PolicyDefinition]) -> str:
        if history_mode in {"local", "cloud"}:
            return "history"
        model_tier = None
        if policy:
            model_tier = policy.actions.get("extraction", {}).get("model_tier")
        if model_tier in {"local", "cloud"}:
            return "policy"
        return "default"
