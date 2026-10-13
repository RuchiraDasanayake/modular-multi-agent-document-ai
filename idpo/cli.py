"""Command-line interface for the IDPO document processing pipeline."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from idpo.agents.intake import IntakeAgent
from idpo.core.config import load_config
from idpo.core.preflight import run_preflight
from idpo.core.provenance import export_provenance
from idpo.core.storage import migrate_legacy_runtime_data
from idpo.evaluation.runner import evaluate_documents
from idpo.pipeline.inbox import process_inbox
from idpo.pipeline.orchestrator import Pipeline
from idpo.pipeline.serialization import document_to_dict, result_to_dict
from idpo.retrieval.index_bundle import IndexBundle

SUPPORTED_INPUT_EXTS = {".json", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def _bounded_model_integer(raw: str, maximum: int) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", raw):
        raise argparse.ArgumentTypeError(f"Expected an integer from 1 to {maximum}")
    value = int(raw)
    if value > maximum:
        raise argparse.ArgumentTypeError(f"Expected an integer from 1 to {maximum}")
    return value


def _model_timeout_s(raw: str) -> int:
    return _bounded_model_integer(raw, 600)


def _model_max_tokens(raw: str) -> int:
    return _bounded_model_integer(raw, 16384)

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

    inbox_parser = subparsers.add_parser("process-inbox", help="Process inputs/inbox into a run layout and move files")
    inbox_parser.add_argument("--root", default=".", help="Project root for relative paths; runtime storage uses IDPO_DATA_DIR")
    inbox_parser.add_argument("--config", default=None)
    inbox_parser.add_argument("--input-dir", default=None, help="Optional directory to process directly instead of the managed inbox")
    inbox_parser.add_argument("--run-id", default=None, help="Optional explicit run id")
    inbox_parser.add_argument("--fields-file", default=None, help="Optional JSON file containing extraction field definitions")
    inbox_parser.add_argument(
        "--output-mode",
        default="summary",
        choices=("summary", "full"),
        help="Print a summary payload or the full process_inbox result as JSON",
    )

    auto_parser = subparsers.add_parser("process-auto", help="Discover fields and extract source-grounded values")
    auto_parser.add_argument("--input", required=True, help="One document or a directory of documents")
    auto_parser.add_argument("--run-id", default=None)
    auto_parser.add_argument("--ocr-engine", default="tesseract",
                             choices=("tesseract", "paddle", "paddleocr", "rapidocr"))
    auto_parser.add_argument("--ocr-lang", default="eng")
    auto_parser.add_argument("--ocr-call-timeout-s", type=float, default=30.0)
    auto_parser.add_argument("--ocr-page-budget-s", type=float, default=120.0)
    auto_parser.add_argument("--model", default=None, help="Optional OpenAI-compatible model ID")
    auto_parser.add_argument("--api-base-url", default=None, help="HTTPS model endpoint or local HTTP endpoint")
    auto_parser.add_argument("--api-key-env", default="ICORE_API_KEY", help="Environment variable containing the API key")
    auto_parser.add_argument("--timeout-s", type=_model_timeout_s, default=60)
    auto_parser.add_argument("--max-tokens", type=_model_max_tokens, default=1200)
    auto_parser.add_argument("--response-format-profile", default="plain_json",
                             choices=("plain_json", "strict_confirmed_values_v1"))
    auto_parser.add_argument("--approved-recipe-file", default=None, help="Explicit approved recipe snapshot file")
    auto_parser.add_argument("--approved-recipe-sha256", default=None, help="Expected SHA-256 of recipe snapshot bytes")
    auto_parser.add_argument("--confirmed-schema-file", default=None, help="Explicit user-confirmed schema snapshot file")
    auto_parser.add_argument("--confirmed-schema-sha256", default=None, help="Expected SHA-256 of confirmed schema bytes")

    migrate_parser = subparsers.add_parser("migrate-storage", help="Move legacy repo-root runtime data into IDPO_DATA_DIR")
    migrate_parser.add_argument("--root", default=".", help="Legacy repo root containing runs/ and inputs/")
    migrate_parser.add_argument("--data-root", default=None, help="Override target data root (defaults to IDPO_DATA_DIR)")

    query_parser = subparsers.add_parser("query", help="Query an existing run index")
    query_parser.add_argument("--run-dir", required=True)
    query_parser.add_argument("--question", required=True)
    query_parser.add_argument("--doc-id", default=None)
    query_parser.add_argument("--section", default=None)

    eval_parser = subparsers.add_parser("evaluate", help="Run evaluation suite")
    eval_parser.add_argument("--input", required=True)
    eval_parser.add_argument("--run-dir", required=True)
    eval_parser.add_argument("--config", default=None)

    prov_parser = subparsers.add_parser("export-provenance", help="Export provenance JSON")
    prov_parser.add_argument("--run-dir", required=True)
    prov_parser.add_argument("--out", required=True)

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
        return

    if args.command == "process-inbox":
        file_paths = None
        extraction_fields = None
        if args.input_dir:
            input_dir = Path(args.input_dir)
            if not input_dir.exists():
                raise SystemExit(f"Input directory does not exist: {input_dir}")
            file_paths = [
                str(path)
                for path in sorted(input_dir.iterdir())
                if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTS
            ]
            if not file_paths:
                raise SystemExit(f"No supported files found in {input_dir}")
        if args.fields_file:
            fields_path = Path(args.fields_file)
            if not fields_path.exists():
                raise SystemExit(f"Fields file does not exist: {fields_path}")
            extraction_fields = json.loads(fields_path.read_text(encoding="utf-8"))
            if not isinstance(extraction_fields, list):
                raise SystemExit("Fields file must contain a JSON array")
        result = process_inbox(
            Path(args.root),
            args.config,
            extraction_fields=extraction_fields,
            run_id=args.run_id,
            file_paths=file_paths,
        )
        payload = result if args.output_mode == "full" else {"run_id": result["run_id"], "run_dir": result["run_dir"]}
        print(json.dumps(payload, indent=2))
        return

    if args.command == "process-auto":
        from idpo.product_auto import process_auto
        from idpo.product_auto.approved_recipe import load_approved_recipe
        from idpo.product_auto.confirmed_schema import load_confirmed_schema
        from idpo.product_auto.provider import OpenAICompatibleChat

        if bool(args.model) != bool(args.api_base_url):
            parser.error("--model and --api-base-url must be supplied together")
        if bool(args.approved_recipe_file) != bool(args.approved_recipe_sha256):
            parser.error("--approved-recipe-file and --approved-recipe-sha256 must be supplied together")
        if bool(args.confirmed_schema_file) != bool(args.confirmed_schema_sha256):
            parser.error("--confirmed-schema-file and --confirmed-schema-sha256 must be supplied together")
        if args.approved_recipe_file and args.confirmed_schema_file:
            parser.error("Choose either an approved recipe or a confirmed schema")
        if (args.approved_recipe_file or args.confirmed_schema_file) and not args.model:
            parser.error("An approved recipe or confirmed schema requires a configured value extraction model")
        approved_recipe = (
            load_approved_recipe(Path(args.approved_recipe_file), args.approved_recipe_sha256)
            if args.approved_recipe_file else None
        )
        confirmed_schema = (
            load_confirmed_schema(Path(args.confirmed_schema_file), args.confirmed_schema_sha256)
            if args.confirmed_schema_file else None
        )
        model = (
            OpenAICompatibleChat(
                base_url=args.api_base_url,
                model=args.model,
                api_key_env=args.api_key_env,
                timeout_s=args.timeout_s,
                max_tokens=args.max_tokens,
            )
            if args.model
            else None
        )
        result = process_auto(
            args.input,
            run_id=args.run_id,
            model=model,
            ocr_engine=args.ocr_engine,
            ocr_lang=args.ocr_lang,
            ocr_call_timeout_s=args.ocr_call_timeout_s,
            ocr_page_budget_s=args.ocr_page_budget_s,
            approved_recipe=approved_recipe,
            confirmed_schema=confirmed_schema,
            response_format_profile=args.response_format_profile,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "migrate-storage":
        payload = migrate_legacy_runtime_data(source_repo_root=Path(args.root), target_data_root=args.data_root)
        print(json.dumps(payload, indent=2))
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

    if args.command == "export-provenance":
        base_dir, primary_dir = _resolve_run_dirs(Path(args.run_dir))
        export_provenance(str(primary_dir / "provenance" / "events.jsonl"), args.out)
        return

if __name__ == "__main__":
    main()
