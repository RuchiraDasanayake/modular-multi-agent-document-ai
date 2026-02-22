from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from idpo.agents.answering import AnsweringAgent
from idpo.agents.retrieval_agent import RetrievalAgent
from idpo.core.metrics import cer, f1_for_sets, ndcg, wer
from idpo.core.types import Document
from idpo.pipeline.orchestrator import Pipeline, PipelineResult


def evaluate_documents(docs: List[Document], pipeline: Pipeline, run_dir: str) -> Dict[str, Any]:
    started = time.time()
    results = pipeline.process_documents(docs)
    bundle = pipeline.build_index(results, directory=f"{run_dir}/index")

    doc_metrics: List[Dict[str, Any]] = []
    query_metrics: List[Dict[str, Any]] = []
    retrieval_ranks: List[int] = []
    ndcg_scores: List[float] = []
    grounded_scores: List[bool] = []
    citation_scores: List[bool] = []

    retrieval_agent = RetrievalAgent()
    answering_agent = AnsweringAgent()

    for doc, result in zip(docs, results):
        ground = doc.metadata.get("ground_truth", {})
        ocr_truth = ground.get("ocr_text", "")
        ocr_pred = "\n".join(page.text for page in doc.pages)
        ocr_cer = cer(ocr_truth, ocr_pred) if ocr_truth else 0.0
        ocr_wer = wer(ocr_truth, ocr_pred) if ocr_truth else 0.0

        gt_entities = {f"{item['key']}::{item['value']}" for item in ground.get("entities", [])}
        pred_entities = set()
        for entity in result.entities:
            value = result.normalized_entities.get(entity.key, entity.value)
            pred_entities.add(f"{entity.key}::{value}")
        ent_precision, ent_recall, ent_f1 = f1_for_sets(gt_entities, pred_entities)

        gt_sections = set(ground.get("sections", []))
        pred_sections = {section.name for section in result.sections}
        sec_precision, sec_recall, sec_f1 = f1_for_sets(gt_sections, pred_sections)

        chunk_boundary_f1 = _chunk_boundary_f1(result, ground)
        doc_metrics.append(
            {
                "doc_id": doc.doc_id,
                "ocr_cer": ocr_cer,
                "ocr_wer": ocr_wer,
                "entity_precision": ent_precision,
                "entity_recall": ent_recall,
                "entity_f1": ent_f1,
                "section_precision": sec_precision,
                "section_recall": sec_recall,
                "section_f1": sec_f1,
                "chunk_boundary_f1": chunk_boundary_f1,
                "embedding_drift_cosine": None,
                "embedding_drift_l2": None,
                "latency_ms": result.latency_ms,
            }
        )

        for query in ground.get("queries", []):
            question = query.get("question", "")
            expected_answer = str(query.get("answer", "")).strip()
            expected_doc = query.get("doc_id", doc.doc_id)
            expected_section = query.get("expected_section")

            retrieval_result = retrieval_agent.run(
                {
                    "query": question,
                    "bundle": bundle,
                    "filters": {"doc_id": expected_doc} if expected_doc else None,
                },
                pipeline.ctx,
            )
            retrieval_results = retrieval_result.artifacts["retrieval_results"]
            ranks = _ranks_for_expected(retrieval_results, expected_doc, expected_section)
            first_rank = ranks[0] if ranks else 0
            retrieval_ranks.append(first_rank or 0)
            relevant_flags = [1.0 if item.rank in ranks else 0.0 for item in retrieval_results]
            ndcg_scores.append(ndcg(relevant_flags))

            context_chunks = retrieval_result.artifacts["context_chunks"]
            answer_result = answering_agent.run(
                {
                    "question": question,
                    "context_chunks": context_chunks,
                    "entities": result.entities,
                    "signals": [retrieval_result.artifacts.get("signal")],
                    "min_confidence": pipeline.config.answering.min_confidence,
                },
                pipeline.ctx,
            )
            answer = answer_result.artifacts["answer"]

            grounded = expected_answer.lower() in answer.answer.lower() if expected_answer else False
            cited = any(cite.get("doc_id") == expected_doc for cite in answer.citations)
            grounded_scores.append(grounded)
            citation_scores.append(cited)

            query_metrics.append(
                {
                    "doc_id": doc.doc_id,
                    "question": question,
                    "expected_answer": expected_answer,
                    "retrieval_rank": first_rank,
                    "grounded": grounded,
                    "cited": cited,
                }
            )

    retrieval_mrr = (
        sum((1.0 / rank) if rank else 0.0 for rank in retrieval_ranks) / len(retrieval_ranks)
        if retrieval_ranks
        else 0.0
    )
    retrieval_recall = (
        sum(1 for rank in retrieval_ranks if rank and rank <= 5) / len(retrieval_ranks)
        if retrieval_ranks
        else 0.0
    )

    total_latency = sum(result.latency_ms for result in results)
    total_cost = _sum_cost_units(Path(run_dir) / "provenance.jsonl")
    elapsed = (time.time() - started) * 1000
    return {
        "doc_metrics": doc_metrics,
        "query_metrics": query_metrics,
        "retrieval_mrr": retrieval_mrr,
        "retrieval_ndcg": sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0,
        "retrieval_recall_at_5": retrieval_recall,
        "qa_grounded_accuracy": sum(1 for item in grounded_scores if item) / len(grounded_scores) if grounded_scores else 0.0,
        "qa_citation_accuracy": sum(1 for item in citation_scores if item) / len(citation_scores) if citation_scores else 0.0,
        "throughput_docs_per_sec": len(results) / (elapsed / 1000) if elapsed else 0.0,
        "latency_ms_total": total_latency,
        "total_cost_units": total_cost,
        "avg_cost_units_per_doc": total_cost / len(results) if results else 0.0,
        "error_propagation": _error_propagation_report(results, docs),
    }


def _ranks_for_expected(results, expected_doc: str, expected_section: str | None) -> List[int]:
    ranks = []
    for item in results:
        if item.chunk.doc_id != expected_doc:
            continue
        if expected_section and item.chunk.section != expected_section:
            continue
        ranks.append(item.rank)
    return ranks


def _sum_cost_units(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0.0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            total += float(payload.get("cost_units", 0.0))
    return total


def _error_propagation_report(results: List[PipelineResult], docs: List[Document]) -> List[Dict[str, Any]]:
    report = []
    for doc, result in zip(docs, results):
        signal_map = {}
        for signal in result.stage_signals:
            signal_map.setdefault(signal.stage, []).append(signal.confidence)
        def _avg(stage: str) -> float:
            values = signal_map.get(stage, [])
            return sum(values) / len(values) if values else 0.0

        ground = doc.metadata.get("ground_truth", {})
        gt_entities = {f"{item['key']}::{item['value']}" for item in ground.get("entities", [])}
        pred_entities = {f"{entity.key}::{entity.value}" for entity in result.entities}
        _, _, ent_f1 = f1_for_sets(gt_entities, pred_entities)

        report.append(
            {
                "doc_id": doc.doc_id,
                "analysis_confidence": _avg("document_analysis"),
                "preprocess_confidence": min(signal_map.get("ocr", []) + signal_map.get("denoise", []) + signal_map.get("deskew", []) or [0.0]),
                "validation_confidence": _avg("validation"),
                "entity_f1": ent_f1,
                "issue_count": len(result.validation_issues),
            }
        )
    return report


def _chunk_boundary_f1(result: PipelineResult, ground: Dict[str, Any]) -> float | None:
    boundaries = ground.get("chunk_boundaries")
    if not boundaries:
        return None
    if not result.chunks:
        return 0.0
    predicted = []
    total = 0
    for chunk in result.chunks:
        total += chunk.tokens
        predicted.append(total)
    _, _, f1 = f1_for_sets(set(boundaries), set(predicted))
    return f1
