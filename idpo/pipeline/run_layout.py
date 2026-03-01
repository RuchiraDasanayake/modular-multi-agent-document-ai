from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


RUN_SUBDIRS = [
    "input",
    "dae",
    "route",
    "preprocess",
    "extract",
    "validate",
    "recover",
    "escalate",
    "index",
    "retrieve",
    "answer",
    "provenance",
    "metrics",
    "shadow",
    "reports",
]


class RunLayout:
    """Canonical run-folder writer for IDPO outputs."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.ensure()

    def ensure(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for sub in RUN_SUBDIRS:
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)

    def write_input_manifest(self, docs: Iterable[Dict[str, Any]]) -> None:
        path = self.run_dir / "input" / "manifest.json"
        path.write_text(json.dumps({"documents": list(docs)}, indent=2), encoding="utf-8")

    def write_stage_doc(self, stage: str, doc_id: str, payload: Dict[str, Any]) -> str:
        target = self.run_dir / stage
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{doc_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def write_metrics(self, payload: Dict[str, Any], filename: str = "metrics.json") -> str:
        path = self.run_dir / "metrics" / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def append_comparison(self, item: Dict[str, Any], filename: str = "comparisons.json") -> str:
        path = self.run_dir / "metrics" / filename
        items = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, list):
                    items = existing
            except Exception:
                items = []
        items.append(item)
        path.write_text(json.dumps(items, indent=2), encoding="utf-8")
        return str(path)

    def write_shadow_doc(self, policy_id: str, doc_id: str, payload: Dict[str, Any]) -> str:
        target = self.run_dir / "shadow" / policy_id
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{doc_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def write_provenance_bundle(self, events_path: Path, graph_path: Path) -> Dict[str, str]:
        provenance_dir = self.run_dir / "provenance"
        provenance_dir.mkdir(parents=True, exist_ok=True)
        events_copy = provenance_dir / "events.jsonl"
        graph_copy = provenance_dir / "graph.json"
        if events_path.exists():
            events_copy.write_text(events_path.read_text(encoding="utf-8"), encoding="utf-8")
        if graph_path.exists():
            graph_copy.write_text(graph_path.read_text(encoding="utf-8"), encoding="utf-8")
        summary_path = provenance_dir / "summary.md"
        summary_path.write_text(_provenance_summary(events_copy), encoding="utf-8")
        return {"events": str(events_copy), "graph": str(graph_copy), "summary": str(summary_path)}


def _provenance_summary(events_path: Path) -> str:
    if not events_path.exists():
        return "# Provenance Summary\n\nNo provenance events found.\n"

    event_counts = Counter()
    agent_counts = Counter()
    per_doc = defaultdict(Counter)
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            event_type = row.get("event_type", "unknown")
            event_counts[event_type] += 1
            agent_counts[row.get("agent", "unknown")] += 1
            doc_id = row.get("inputs", {}).get("doc_id")
            if doc_id:
                per_doc[str(doc_id)][event_type] += 1

    lines: List[str] = []
    lines.append("# Provenance Summary")
    lines.append("")
    lines.append("## Event Types")
    for name, count in sorted(event_counts.items()):
        lines.append(f"- `{name}`: {count}")
    lines.append("")
    lines.append("## Agents")
    for name, count in sorted(agent_counts.items()):
        lines.append(f"- `{name}`: {count}")
    lines.append("")
    lines.append("## Per-Document Decisions")
    for doc_id, counters in sorted(per_doc.items()):
        snapshot = ", ".join(f"{name}={count}" for name, count in sorted(counters.items()))
        lines.append(f"- `{doc_id}`: {snapshot}")
    lines.append("")
    return "\n".join(lines) + "\n"
