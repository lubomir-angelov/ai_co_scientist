"""CLI entrypoint: ``python -m paper_ingest {ocr|ingest|status}``.

This module does the only wiring the batch needs: it builds the real tools/engine/config,
drives the GPU-tenant preflight for the phase it's about to run, and calls into
``paper_ingest.phases``. It never talks to Docker — the root Makefile owns container
lifecycle; this module only verifies state and fails fast when it's wrong.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from engine.factory import create_llm_engine
from paper_ingest.identity import discover
from paper_ingest.phases import render_status, render_summary, run_ingest_phase, run_ocr_phase
from paper_ingest.preflight import (
    require_down,
    wait_llm_serving,
    wait_memory_ready,
    wait_ocr_documents_ready,
    wait_ocr_ready,
)
from paper_ingest.state import StateStore
from runtime_config import RuntimeConfig
from tools.document_parser_ocr.documents_client import OcrDocumentsClient
from tools.document_parser_ocr.tool import Document_Parser_OCR_Tool
from tools.memory_graph.tool import Memory_Graph_Tool

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper_ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ocr_parser = subparsers.add_parser("ocr", help="Phase 1: OCR every PDF in --input-dir")
    ocr_parser.add_argument("--input-dir", required=True, type=Path)
    ocr_parser.add_argument("--work-dir", required=True, type=Path)
    ocr_parser.add_argument(
        "--exclude", action="append", default=[], metavar="NAME", help="Exact basename; repeatable."
    )
    ocr_parser.add_argument(
        "--reocr",
        action="append",
        default=[],
        metavar="PAPER_ID",
        help="Exact paper id; repeatable. Re-OCR even if state says done "
        "(e.g. stored document fails integrity).",
    )
    ocr_parser.add_argument("--ocr-timeout-seconds", required=True, type=float)
    ocr_parser.add_argument("--ready-timeout-seconds", required=True, type=float)

    ingest_parser = subparsers.add_parser(
        "ingest", help="Phase 2: metadata + memory ingest from the OCR document store"
    )
    ingest_parser.add_argument("--work-dir", required=True, type=Path)
    ingest_parser.add_argument("--ingest-seconds-per-page", required=True, type=float)
    ingest_parser.add_argument("--ready-timeout-seconds", required=True, type=float)

    status_parser = subparsers.add_parser("status", help="Show per-paper ingestion state")
    status_parser.add_argument("--work-dir", required=True, type=Path)

    return parser


def _setup_logging(work_dir: Path | None, phase: str) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if work_dir is not None:
        logs_dir = work_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        file_handler = logging.FileHandler(logs_dir / f"{phase}-{timestamp}.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def _run_ocr(args: argparse.Namespace, cfg: RuntimeConfig) -> int:
    identities = discover(args.input_dir, exclude=args.exclude)
    logger.info("Discovered %d PDF(s) in %s", len(identities), args.input_dir)

    # Locked for the whole phase, including preflight: a second run started against the same
    # work dir must fail fast on the lock, not spend `ready_timeout_seconds` polling first.
    store = StateStore(args.work_dir)
    tool = Document_Parser_OCR_Tool()
    documents = OcrDocumentsClient(cfg.ocr_documents_base_url, cfg.ocr_request_timeout_seconds)
    with store.exclusive_lock():
        require_down("LLM gateway", f"{cfg.llm_base_url}/models", "llm-down")
        wait_ocr_ready(cfg.ocr_base_url, args.ready_timeout_seconds)
        wait_ocr_documents_ready(cfg.ocr_documents_base_url, args.ready_timeout_seconds)
        summary = run_ocr_phase(
            identities, tool, documents, store, args.ocr_timeout_seconds, frozenset(args.reocr)
        )
    logger.info("Phase 1 (OCR) finished:\n%s", render_summary(summary))
    return summary.exit_code


def _run_ingest(args: argparse.Namespace, cfg: RuntimeConfig) -> int:
    # Locked for the whole phase, including preflight — see _run_ocr.
    store = StateStore(args.work_dir)
    engine = create_llm_engine(is_multimodal=False)
    memory_tool = Memory_Graph_Tool()
    documents = OcrDocumentsClient(cfg.ocr_documents_base_url, cfg.ocr_request_timeout_seconds)
    with store.exclusive_lock():
        require_down("OCR", f"{cfg.ocr_base_url}/healthz", "ocr-down")
        wait_llm_serving(
            cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model, args.ready_timeout_seconds
        )
        wait_memory_ready(cfg.memory_base_url, args.ready_timeout_seconds)
        wait_ocr_documents_ready(cfg.ocr_documents_base_url, args.ready_timeout_seconds)
        summary = run_ingest_phase(
            engine, memory_tool, documents, store, args.ingest_seconds_per_page
        )
    logger.info("Phase 2 (ingest) finished:\n%s", render_summary(summary))
    return summary.exit_code


def _run_status(args: argparse.Namespace) -> int:
    store = StateStore(args.work_dir)
    print(render_status(store))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _setup_logging(args.work_dir if args.command != "status" else None, args.command)

    if args.command == "status":
        return _run_status(args)

    cfg = RuntimeConfig.from_env()
    if args.command == "ocr":
        return _run_ocr(args, cfg)
    return _run_ingest(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
