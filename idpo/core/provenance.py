from __future__ import annotations

import json
import time
import uuid
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ProvenanceEvent:
    event_id: str
    timestamp: float
    event_type: str
    agent: str
    version: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    parameters: Dict[str, Any]
    latency_ms: float
    cost_units: float
    artifacts: List[str] = field(default_factory=list)


@dataclass
class ProvenanceGraph:
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, Any]] = field(default_factory=list)

    def add_node(self, node_id: str, node_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "type": node_type, "metadata": metadata or {}}

    def add_edge(self, source: str, target: str, edge_type: str) -> None:
        self.edges.append({"source": source, "target": target, "type": edge_type})

    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": list(self.nodes.values()), "edges": self.edges}


class ProvenanceRecorder:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.graph_path = self.path.with_name("provenance_graph.json")
        self.graph = ProvenanceGraph()
        self._lock = threading.Lock()

    def record(
        self,
        agent: str,
        version: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        parameters: Dict[str, Any],
        artifacts: Optional[List[str]] = None,
        latency_ms: float = 0.0,
        cost_units: float = 0.0,
        event_type: str = "OperatorExecution",
    ) -> ProvenanceEvent:
        event = ProvenanceEvent(
            event_id=uuid.uuid4().hex,
            timestamp=time.time(),
            event_type=event_type,
            agent=agent,
            version=version,
            inputs=inputs,
            outputs=outputs,
            parameters=parameters,
            latency_ms=latency_ms,
            cost_units=cost_units,
            artifacts=artifacts or [],
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.__dict__, sort_keys=True) + "\n")
            self._update_graph(event)
            self._persist_graph()
        return event

    def register_chunks(self, doc_id: str, chunks: List[Dict[str, Any]]) -> None:
        with self._lock:
            for chunk in chunks:
                node_id = f"chunk:{chunk['chunk_id']}"
                self.graph.add_node(
                    node_id,
                    "chunk",
                    {
                        "doc_id": doc_id,
                        "page_range": chunk.get("page_range"),
                        "section": chunk.get("section"),
                    },
                )
            self._persist_graph()

    def _update_graph(self, event: ProvenanceEvent) -> None:
        run_id = f"run:{event.event_id}"
        self.graph.add_node(
            run_id,
            "agent_run",
            {
                "agent": event.agent,
                "version": event.version,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
            },
        )

        doc_id = event.inputs.get("doc_id")
        if doc_id:
            doc_node = f"doc:{doc_id}"
            self.graph.add_node(doc_node, "document", {"doc_id": doc_id})
            self.graph.add_edge(doc_node, run_id, "used_by")

        for artifact_id in event.inputs.get("input_artifacts", []):
            node_id = f"artifact:{artifact_id}"
            self.graph.add_node(node_id, "artifact", {"artifact_id": artifact_id})
            self.graph.add_edge(node_id, run_id, "used_by")

        for chunk_id in event.inputs.get("chunk_ids", []):
            chunk_node = f"chunk:{chunk_id}"
            self.graph.add_node(chunk_node, "chunk", {"chunk_id": chunk_id})
            self.graph.add_edge(chunk_node, run_id, "used_by")

        for artifact_id in event.outputs.get("output_artifacts", []):
            node_id = f"artifact:{artifact_id}"
            self.graph.add_node(node_id, "artifact", {"artifact_id": artifact_id})
            self.graph.add_edge(run_id, node_id, "produced_by")

        for chunk_id in event.outputs.get("chunk_ids", []):
            chunk_node = f"chunk:{chunk_id}"
            self.graph.add_node(chunk_node, "chunk", {"chunk_id": chunk_id})
            self.graph.add_edge(run_id, chunk_node, "produced_by")

        decisions = event.outputs.get("decisions", [])
        if decisions:
            decision_id = f"decision:{event.event_id}"
            self.graph.add_node(decision_id, "decision", {"count": len(decisions)})
            self.graph.add_edge(run_id, decision_id, "produced_by")
            for item in decisions:
                chunk_id = item.get("chunk_id")
                if not chunk_id:
                    continue
                chunk_node = f"chunk:{chunk_id}"
                self.graph.add_node(chunk_node, "chunk", {"chunk_id": chunk_id})
                edge_type = "selected" if item.get("selected") else "dropped"
                self.graph.add_edge(decision_id, chunk_node, edge_type)

        citations = event.outputs.get("citations", [])
        if citations:
            answer_id = f"answer:{event.event_id}"
            self.graph.add_node(answer_id, "answer", {"question": event.inputs.get("question"), "confidence": event.outputs.get("confidence")})
            self.graph.add_edge(run_id, answer_id, "produced_by")
            for cite in citations:
                chunk_id = cite.get("chunk_id")
                if not chunk_id:
                    continue
                chunk_node = f"chunk:{chunk_id}"
                self.graph.add_node(chunk_node, "chunk", {"chunk_id": chunk_id})
                self.graph.add_edge(answer_id, chunk_node, "references")

    def _persist_graph(self) -> None:
        self.graph_path.write_text(json.dumps(self.graph.to_dict(), indent=2), encoding="utf-8")


def export_provenance(path: str, out_path: str) -> None:
    events = []
    path_obj = Path(path)
    with path_obj.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(json.loads(line))
    graph_path = path_obj.with_name("provenance_graph.json")
    graph = {}
    if graph_path.exists():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    Path(out_path).write_text(json.dumps({"events": events, "graph": graph}, indent=2), encoding="utf-8")
