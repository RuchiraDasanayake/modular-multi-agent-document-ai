from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from idpo.agents.intake import IntakeAgent
from idpo.core.calibration import ConfidenceCalibrator, load_calibration_samples
from idpo.core.config import load_config
from idpo.core.preflight import run_preflight
from idpo.core.provenance import export_provenance
from idpo.evaluation.runner import evaluate_documents
from idpo.pipeline.orchestrator import Pipeline
from idpo.pipeline.serialization import document_to_dict, result_to_dict
from idpo.pipeline.inbox import process_inbox
from idpo.retrieval.index_bundle import IndexBundle


SUPPORTED_INPUT_EXTS = {".json", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def main() -> None:
    parser = argparse.ArgumentParser(prog="idpo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents into normalized JSON")
    ingest_parser.add_argument("--input", required=True)
    ingest_parser.add_argument("--out", required=True)

    process_parser = subparsers.add_parser("process", help="Process documents and build index")
    process_parser.add_argument("--input", required=True)
    process_parser.add_argument("--run-dir", required=True)
    process_parser.add_argument("--config", default=None)
    process_parser.add_argument("--excel-out", default=None)
    process_parser.add_argument("--simple-output-dir", default=None, help="Write simple outputs under this folder")

    simple_parser = subparsers.add_parser("process-simple", help="Process documents with a simple output layout")
    simple_parser.add_argument("--input", required=True)
    simple_parser.add_argument("--config", default=None)

    dropbox_parser = subparsers.add_parser("process-dropbox", help="Process a drop folder and move inputs to processed/")
    dropbox_parser.add_argument("--input-dir", required=True)
    dropbox_parser.add_argument("--config", default=None)

    inbox_parser = subparsers.add_parser("process-inbox", help="Process inputs/inbox into a run layout and move files")
    inbox_parser.add_argument("--root", default=".", help="Repo root with inputs/ and runs/")
    inbox_parser.add_argument("--config", default=None)

    query_parser = subparsers.add_parser("query", help="Query an existing run index")
    query_parser.add_argument("--run-dir", required=True)
    query_parser.add_argument("--question", required=True)
    query_parser.add_argument("--doc-id", default=None)
    query_parser.add_argument("--section", default=None)

    eval_parser = subparsers.add_parser("evaluate", help="Run evaluation suite")
    eval_parser.add_argument("--input", required=True)
    eval_parser.add_argument("--run-dir", required=True)
    eval_parser.add_argument("--config", default=None)

    hooks_parser = subparsers.add_parser("evaluate-hooks", help="Compare routes or strategies")
    hooks_parser.add_argument("--input", required=True)
    hooks_parser.add_argument("--run-dir", required=True)
    hooks_parser.add_argument("--configs", required=True, help="Comma-separated list of config files")
    hooks_parser.add_argument("--mode", choices=["preprocess", "retrieval"], required=True)

    prov_parser = subparsers.add_parser("export-provenance", help="Export provenance JSON")
    prov_parser.add_argument("--run-dir", required=True)
    prov_parser.add_argument("--out", required=True)

    calibrate_fit_parser = subparsers.add_parser("calibrate-fit", help="Fit confidence calibrator from JSONL")
    calibrate_fit_parser.add_argument("--dataset", required=True, help="JSONL with score/label pairs")
    calibrate_fit_parser.add_argument("--out", required=True, help="Output calibrator JSON path")
    calibrate_fit_parser.add_argument("--method", choices=["platt", "isotonic"], default="platt")
    calibrate_fit_parser.add_argument("--bins", type=int, default=10)
    calibrate_fit_parser.add_argument("--report", default=None, help="Optional evaluation report JSON output")

    calibrate_eval_parser = subparsers.add_parser("calibrate-eval", help="Evaluate confidence calibrator")
    calibrate_eval_parser.add_argument("--dataset", required=True, help="JSONL with score/label pairs")
    calibrate_eval_parser.add_argument("--model", required=True, help="Calibrator JSON path")
    calibrate_eval_parser.add_argument("--out", required=True, help="Evaluation report JSON path")
    calibrate_eval_parser.add_argument("--bins", type=int, default=10)

    args = parser.parse_args()
    intake = IntakeAgent()

    def _resolve_run_dirs(path: Path) -> tuple[Path, Path]:
        base = path
        if (base / "run_metadata.json").exists():
            primary = base / "primary" if (base / "primary").exists() else base
            return base, primary
        if base.name == "primary" and (base.parent / "run_metadata.json").exists():
            return base.parent, base
        return base, base

    if args.command == "ingest":
        docs = intake.ingest(args.input)
        payload = {"documents": [document_to_dict(doc) for doc in docs]}
        Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return

    if args.command == "process":
        config = load_config(args.config)
        run_preflight(config)
        pipeline = Pipeline(config=config, run_dir=args.run_dir)
        docs = intake.ingest(args.input)
        results = pipeline.process_documents(docs)
        pipeline.build_index(results, directory=str(pipeline.run_dir / "index"))
        out_path = pipeline.run_dir / "results.json"
        out_path.write_text(
            json.dumps({"results": [result_to_dict(result) for result in results]}, indent=2),
            encoding="utf-8",
        )
        excel_out = args.excel_out or str(pipeline.run_dir / "entities.xlsx")
        pipeline.export_structured_results(results, excel_out)
        if args.simple_output_dir:
            pipeline.export_simple_workspace(docs, results, args.simple_output_dir)
        return

    if args.command == "process-simple":
        config = load_config(args.config)
        run_preflight(config)
        input_dir = Path(args.input)
        output_dir = input_dir / "output"
        pipeline = Pipeline(config=config, run_dir=str(output_dir))
        docs = intake.ingest(args.input)
        results = pipeline.process_documents(docs)
        pipeline.build_index(results, directory=str(pipeline.run_dir / "index"))
        out_path = pipeline.run_dir / "results.json"
        out_path.write_text(
            json.dumps({"results": [result_to_dict(result) for result in results]}, indent=2),
            encoding="utf-8",
        )
        excel_out = str(pipeline.run_dir / "entities.xlsx")
        pipeline.export_structured_results(results, excel_out)
        pipeline.export_simple_workspace(docs, results, str(pipeline.run_dir))
        return

    if args.command == "process-dropbox":
        config = load_config(args.config)
        config.shadow.enabled = False
        run_preflight(config)
        input_dir = Path(args.input_dir)
        processed_dir = input_dir / "processed"
        outputs_root = input_dir / "outputs"
        processed_dir.mkdir(parents=True, exist_ok=True)
        outputs_root.mkdir(parents=True, exist_ok=True)

        files = [
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTS
        ]
        if not files:
            raise SystemExit(f"No supported files found in {input_dir}")

        failed: list[str] = []
        for file_path in files:
            try:
                docs = intake.ingest(str(file_path))
                for doc in docs:
                    output_dir = outputs_root / doc.doc_id
                    pipeline = Pipeline(config=config, run_dir=str(output_dir))
                    results = pipeline.process_documents([doc])
                    pipeline.build_index(results, directory=str(pipeline.run_dir / "index"))
                    out_path = pipeline.run_dir / "results.json"
                    out_path.write_text(
                        json.dumps({"results": [result_to_dict(result) for result in results]}, indent=2),
                        encoding="utf-8",
                    )
                    excel_out = str(pipeline.run_dir / "entities.xlsx")
                    pipeline.export_structured_results(results, excel_out)
                    pipeline.export_simple_workspace([doc], results, str(pipeline.run_dir))
                shutil.move(str(file_path), str(processed_dir / file_path.name))
            except Exception:
                failed.append(str(file_path))

        if failed:
            raise SystemExit(f"Failed to process: {', '.join(failed)}")
        return

    if args.command == "process-inbox":
        process_inbox(Path(args.root), args.config)
        return

    if args.command == "query":
        from idpo.agents.answering import AnsweringAgent
        from idpo.agents.retrieval_agent import RetrievalAgent
        from idpo.core.types import Entity, StageSignal

        base_dir, primary_dir = _resolve_run_dirs(Path(args.run_dir))
        run_dir = primary_dir
        metadata_path = base_dir / "run_metadata.json"
        if metadata_path.exists():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            from idpo.core.config import config_from_dict

            config = config_from_dict(payload.get("config", {}))
        else:
            config = load_config(None)
        pipeline = Pipeline(config=config, run_dir=str(base_dir), read_only=True)
        bundle = IndexBundle.load(str(run_dir / "index"))
        retrieval_agent = RetrievalAgent()
        filters = {}
        if args.doc_id:
            filters["doc_id"] = args.doc_id
        if args.section:
            filters["section"] = args.section
        retrieval_result = retrieval_agent.run(
            {"query": args.question, "bundle": bundle, "filters": filters or None},
            pipeline.ctx,
        )
        context_chunks = retrieval_result.artifacts["context_chunks"]

        answer_agent = AnsweringAgent()
        entities = []
        stage_signals = []
        results_path = run_dir / "results.json"
        if results_path.exists() and args.doc_id:
            payload = json.loads(results_path.read_text(encoding="utf-8"))
            for item in payload.get("results", []):
                if item.get("doc_id") == args.doc_id:
                    entities = [Entity(**entity) for entity in item.get("entities", [])]
                    stage_signals = [StageSignal(**signal) for signal in item.get("stage_signals", [])]
                    break
        answer_result = answer_agent.run(
            {
                "question": args.question,
                "context_chunks": context_chunks,
                "entities": entities,
                "signals": [retrieval_result.artifacts.get("signal")] + stage_signals,
                "min_confidence": pipeline.config.answering.min_confidence,
            },
            pipeline.ctx,
        )
        answer = answer_result.artifacts["answer"]
        Path(run_dir / "last_answer.json").write_text(json.dumps(answer.__dict__, indent=2), encoding="utf-8")
        print(json.dumps(answer.__dict__, indent=2))
        return

    if args.command == "evaluate":
        config = load_config(args.config)
        pipeline = Pipeline(config=config, run_dir=args.run_dir)
        docs = intake.ingest(args.input)
        metrics = evaluate_documents(docs, pipeline, str(pipeline.run_dir))
        out_path = Path(pipeline.run_dir) / "evaluation.json"
        out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        return

    if args.command == "evaluate-hooks":
        from idpo.evaluation.hooks import compare_preprocessing_routes, compare_retrieval_strategies

        docs = intake.ingest(args.input)
        config_paths = [path.strip() for path in args.configs.split(",") if path.strip()]
        if args.mode == "preprocess":
            payload = compare_preprocessing_routes(docs, args.run_dir, config_paths)
        else:
            payload = compare_retrieval_strategies(docs, args.run_dir, config_paths)
        out_path = Path(args.run_dir) / "evaluation_hooks.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return

    if args.command == "export-provenance":
        base_dir, primary_dir = _resolve_run_dirs(Path(args.run_dir))
        export_provenance(str(primary_dir / "provenance.jsonl"), args.out)
        return

    if args.command == "calibrate-fit":
        samples = load_calibration_samples(args.dataset)
        calibrator = ConfidenceCalibrator(method=args.method)
        calibrator.fit(samples)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        calibrator.save(args.out)
        report = calibrator.evaluate(samples, bins=args.bins)
        report_path = args.report or str(Path(args.out).with_suffix(".eval.json"))
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"model": args.out, "report": report_path, "count": report.get("count", 0)}, indent=2))
        return

    if args.command == "calibrate-eval":
        samples = load_calibration_samples(args.dataset)
        calibrator = ConfidenceCalibrator.load(args.model)
        report = calibrator.evaluate(samples, bins=args.bins)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"model": args.model, "report": args.out, "count": report.get("count", 0)}, indent=2))
        return


if __name__ == "__main__":
    main()
