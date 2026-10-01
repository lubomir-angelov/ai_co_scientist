"""Typed errors. Every API-visible failure is a VoiceError with a status and a machine code."""

from __future__ import annotations

from typing import ClassVar


class VoiceError(Exception):
    """Base of every error rendered to API clients as ``{"code", "message"}``."""

    status_code: ClassVar[int]
    code: ClassVar[str]


class ConfigError(Exception):
    """Startup configuration is missing or invalid; the process must not start."""


class ModelLoadError(RuntimeError):
    """A baked model could not be loaded; the process must not serve."""


class ModelManifestError(RuntimeError):
    """The baked model manifest is missing, malformed, or points at absent files."""


class ModelsLoadingError(VoiceError):
    status_code = 503
    code = "model_loading"


class ScriptNotPreparedError(VoiceError):
    status_code = 409
    code = "script_not_prepared"


class StoreIntegrityError(VoiceError):
    status_code = 500
    code = "store_integrity_error"


class SectionNotFoundError(VoiceError):
    status_code = 404
    code = "section_not_found"


class SectionNotSpeakableError(VoiceError):
    status_code = 422
    code = "section_not_speakable"


class NothingToSpeakError(VoiceError):
    status_code = 422
    code = "nothing_to_speak"


class RenderQueueFullError(VoiceError):
    status_code = 429
    code = "render_queue_full"


class RenderStaleError(VoiceError):
    status_code = 409
    code = "render_stale"


class RenderNotFoundError(VoiceError):
    status_code = 404
    code = "render_not_found"


class SectionNotRenderedError(VoiceError):
    status_code = 404
    code = "section_not_rendered"


class TooManyStreamsError(VoiceError):
    status_code = 429
    code = "too_many_streams"


class TooManyTranscriptionsError(VoiceError):
    status_code = 429
    code = "too_many_transcriptions"


class UnknownBlockRefError(VoiceError):
    status_code = 422
    code = "unknown_block_ref"

    def __init__(self, ref: str, page_number: int) -> None:
        super().__init__(f"OCR block ref {ref!r} on page {page_number} has no entry in BLOCK_POLICY")
        self.ref = ref
        self.page_number = page_number


class OcrDocumentNotFoundError(VoiceError):
    status_code = 404
    code = "ocr_document_not_found"


class OcrContractError(VoiceError):
    status_code = 502
    code = "ocr_contract_violation"


class OcrServiceError(VoiceError):
    status_code = 502
    code = "ocr_unavailable"


class OcrTimeoutError(VoiceError):
    status_code = 504
    code = "ocr_timeout"


class UploadTooLargeError(VoiceError):
    status_code = 413
    code = "upload_too_large"


class InvalidContentLengthError(VoiceError):
    status_code = 400
    code = "invalid_content_length"


class UnsupportedLanguageError(VoiceError):
    status_code = 422
    code = "unsupported_language"


class UnsupportedMediaTypeError(VoiceError):
    status_code = 415
    code = "unsupported_media_type"


class AudioDecodeError(VoiceError):
    status_code = 422
    code = "audio_undecodable"


class PhonemeWindowError(RuntimeError):
    """A single phoneme token is longer than the model window; it is never clipped."""
