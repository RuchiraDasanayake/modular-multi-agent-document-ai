from __future__ import annotations

import time
from typing import Dict, List, Optional

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Chunk, RetrievalResult, StageSignal, TokenBudget
from idpo.retrieval.context_selector import select_context
from idpo.retrieval.hybrid import HybridRetriever
from idpo.retrieval.index_bundle import IndexBundle


class RetrievalAgent(Agent):
    name = "retrieval"
    version = "v1"
    input_contract = {"query": "str", "bundle": "IndexBundle", "filters": "dict|None"}
    output_contract = {"retrieval_results": "list", "context_chunks": "list", "decisions": "list", "signal": "StageSignal"}

    def run(
        self,
        payload: AgentMessage,
        ctx: AgentContext,
    ) -> AgentResult:
        started = time.time()
        query: str = payload["query"]
        bundle: IndexBundle = payload["bundle"]
        filters: Optional[Dict[str, str]] = payload.get("filters")
        retriever = HybridRetriever(bundle.vector_store, bundle.bm25)
        results = retriever.retrieve(
            query=query,
            chunks=bundle.chunks,
            dense_k=ctx.config.retrieval.dense_k,
            sparse_k=ctx.config.retrieval.sparse_k,
            final_k=ctx.config.retrieval.final_k,
            metadata_boost=ctx.config.retrieval.metadata_boost,
            mmr_lambda=ctx.config.retrieval.mmr_lambda,
        )
        if filters:
            results = [item for item in results if _matches_filters(item.chunk, filters)]

        budget = TokenBudget(
            max_tokens=ctx.config.context.max_tokens,
            reserved_tokens=ctx.config.context.reserved_tokens,
        )
        context_chunks, used_tokens, decisions = select_context(
            results,
            budget=budget,
            diversity_penalty=ctx.config.context.diversity_penalty,
        )
        selection_artifact = ctx.artifact_store.save_json(
            f"retrieval_selection_{ctx.run_id}.json",
            {"decisions": [decision for decision in decisions]},
            kind="selection_log",
            raw=False,
            metadata={"agent": self.name, "version": self.version, "query": query},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if context_chunks else 0.3,
            uncertainty=0.3 if context_chunks else 0.7,
            metadata={"selected": len(context_chunks), "tokens": used_tokens},
        )
        self._record(
            ctx,
            inputs={"query": query, "filters": filters or {}},
            outputs={
                "results": len(results),
                "selected": len(context_chunks),
                "tokens": used_tokens,
                "decisions": decisions,
            },
            parameters={"dense_k": ctx.config.retrieval.dense_k, "sparse_k": ctx.config.retrieval.sparse_k},
            artifacts=[selection_artifact.artifact_id],
            output_artifacts=[selection_artifact.artifact_id],
            started=started,
        )
        return AgentResult(
            artifacts={
                "retrieval_results": results,
                "context_chunks": context_chunks,
                "token_usage": used_tokens,
                "selection_decisions": decisions,
                "signal": signal,
            }
        )


def _matches_filters(chunk: Chunk, filters: Dict[str, str]) -> bool:
    for key, value in filters.items():
        if key == "doc_id" and chunk.doc_id != value:
            return False
        if key == "section" and chunk.section != value:
            return False
    return True
