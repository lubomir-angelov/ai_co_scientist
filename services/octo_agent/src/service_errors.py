"""One error base for every local-service call the batch (or the tools it wraps) makes.

The abort policy in ``paper_ingest.phases`` reads only ``status_code`` — never the
exception's subclass — so this is the single place that attribute is defined (CLAUDE.md §6).
"""

from __future__ import annotations


class ServiceCallError(RuntimeError):
    """A call to a local service failed.

    ``status_code`` is ``None`` when no HTTP response was received at all (connection
    refused, timeout): the service's state for that request is genuinely unknown, which is
    why the batch treats it differently from a definite HTTP error.
    """

    def __init__(self, message: str, *, status_code: int | None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OCRServiceError(ServiceCallError):
    """The OCR service could not be reached, returned an error, or violated its contract."""


class MemoryServiceError(ServiceCallError):
    """The memory service could not be reached, returned an error, or violated its contract."""


class LLMEngineError(ServiceCallError):
    """The local LLM engine could not be reached, returned an error, or gave no content."""
