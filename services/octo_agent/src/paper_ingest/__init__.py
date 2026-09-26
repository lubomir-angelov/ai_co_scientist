"""Two-phase, resumable paper ingestion: ``python -m paper_ingest {ocr|ingest|status}``.

Phase 1 (GPU = OCR) OCRs every PDF in an input directory into a per-paper cache. Phase 2
(GPU = LLM) resolves page-1 metadata and ingests each paper's page sections into memory via
``Memory_Graph_Tool``'s ``ingest_paper`` action. See ``services/octo_agent/README.md``.
"""
