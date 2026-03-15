from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from idpo.agents.intake import IntakeAgent
from idpo.core.config import load_config
from idpo.core.preflight import run_preflight
from idpo.pipeline.orchestrator import Pipeline
from idpo.pipeline.serialization import result_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m idpo.demo")
    parser.add_argument("--input", default="demo_docs", help="Input folder containing demo documents")
    parser.add_argument("--config", default="configs/idpo_research_config.json")
    parser.add_argument("--run-dir", default=None, help="Optional run directory")
    parser.add_argument("--shadow", action="store_true", help="Enable shadow routing with sample_rate=1.0")
    parser.add_argument("--report", action="store_true", help="Write enriched report summary")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        _create_demo_docs(input_dir)

    config = load_config(args.config if Path(args.config).exists() else None)
    if args.shadow:
        config.shadow.enabled = True
        config.shadow.sample_rate = 1.0
        if not config.shadow.candidate_policy_ids:
            config.shadow.candidate_policy_ids = ["default"]
    run_preflight(config)

    run_dir = args.run_dir or str(Path("runs") / f"demo_{int(time.time())}")
    pipeline = Pipeline(config=config, run_dir=run_dir)
    intake = IntakeAgent()
    docs = intake.ingest(str(input_dir))
    results = pipeline.process_documents(docs)
    pipeline.build_index(results, directory=str(pipeline.run_dir / "index"))

    results_path = pipeline.run_dir / "results.json"
    results_path.write_text(
        json.dumps({"results": [result_to_dict(result) for result in results]}, indent=2),
        encoding="utf-8",
    )

    recovered_docs = sum(1 for result in results if result.recovered_fields)
    escalated_docs = sum(1 for result in results if result.escalated)
    shadow_total = sum(len(result.shadow_comparisons) for result in results)
    summary = {
        "run_dir": str(pipeline.run_dir),
        "doc_count": len(results),
        "recovery_docs": recovered_docs,
        "escalation_docs": escalated_docs,
        "shadow_comparisons": shadow_total,
    }

    if args.report:
        report_path = pipeline.run_dir / "reports" / "summary.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Demo Summary",
            "",
            f"- Run directory: `{pipeline.run_dir}`",
            f"- Documents: `{len(results)}`",
            f"- Docs with field-level recovery: `{recovered_docs}`",
            f"- Docs with field-level escalation: `{escalated_docs}`",
            f"- Shadow comparisons generated: `{shadow_total}`",
            "",
            "## Document Outcomes",
        ]
        for result in results:
            lines.append(
                f"- `{result.doc_id}` route={result.route_bin} policy={result.policy_id} "
                f"recovered={len(result.recovered_fields)} escalated={result.escalated}"
            )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))


def _create_demo_docs(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    docs = [
        {
            "doc_id": "demo_image_invoice",
            "source": "scanned",
            "metadata": {
                "vendor": "acme",
                "domain": "finance",
                "skew_angle": 5.5,
                "guardrail_flags": ["approval_code"],
            },
            "pages": [
                {
                    "number": 1,
                    "text": (
                        "Inv0ice ID: INV-1001\n"
                        "Customer Name: Alice Doe\n"
                        "Total Amount USD 1200.00\n"
                        "Due Date 03/10/2026\n"
                        "Please process urgently."
                    ),
                    "raw_text": (
                        "Invoice ID: INV-1001\n"
                        "Customer Name: Alice Doe\n"
                        "Total Amount: USD 1200.00\n"
                        "Due Date: 03/10/2026\n"
                        "Please process urgently."
                    ),
                    "image_path": "scan_invoice.png",
                    "metadata": {"dpi": 220},
                }
            ],
        },
        {
            "doc_id": "demo_table_statement",
            "source": "digital",
            "metadata": {"vendor": "globex", "domain": "operations"},
            "pages": [
                {
                    "number": 1,
                    "text": (
                        "Statement ID: ST-8891\n"
                        "Date: 02/15/2026\n"
                        "Item | Qty | Unit Price | Total\n"
                        "Widget A | 10 | 15.00 | 150.00\n"
                        "Widget B | 4 | 20.00 | 80.00\n"
                        "Total Amount: 230.00\n"
                    ),
                }
            ],
        },
        {
            "doc_id": "demo_clean_text",
            "source": "digital",
            "metadata": {"vendor": "initech", "domain": "hr"},
            "pages": [
                {
                    "number": 1,
                    "text": (
                        "Employee Record\n"
                        "Record ID: EMP-22\n"
                        "Document Date: 01/20/2026\n"
                        "Department: Research\n"
                        "Status: Active\n"
                    ),
                }
            ],
        },
    ]
    for doc in docs:
        path = input_dir / f"{doc['doc_id']}.json"
        path.write_text(json.dumps([doc], indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
