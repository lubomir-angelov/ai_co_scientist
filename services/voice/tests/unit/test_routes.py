import asyncio
import io
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import soundfile as sf
from conftest import (
    FAKE_SAMPLE_RATE,
    SAMPLES_PER_PHONEME,
    UNDECODABLE_MARKER,
    ExitRecorder,
    FakeStt,
    FakeTts,
    load_ocr_fixture,
    make_config,
    make_manifest,
)
from fastapi.testclient import TestClient
from shared_library.data_contracts import OcrDocumentError, OcrDocumentErrorCode

from voice_service.app import create_app
from voice_service.models.schemas import MAX_TRANSCRIPTION_UPLOAD_BYTES, OmittedBlock
from voice_service.services.synthesis import HEADING_PAUSE_SECONDS, OMITTED_BLOCK_PAUSE_SECONDS

DURATION_TOLERANCE_SECONDS = 0.1
# Section 2 ("Methods"): heading, then an omitted table and its caption, then one body block.
SECTION_2_PAUSE_SECONDS = HEADING_PAUSE_SECONDS + 2 * OMITTED_BLOCK_PAUSE_SECONDS

DOC = "paper-1"


class Env:
    def __init__(self, tmp_path: Path, exit_recorder: ExitRecorder, **config_overrides: object) -> None:
        self.config = make_config(tmp_path, **config_overrides)
        self.manifest = make_manifest(tmp_path)
        self.tts = FakeTts()
        self.stt = FakeStt()
        self.exit_recorder = exit_recorder
        self.ocr_handler: Callable[[httpx.Request], httpx.Response] = self._default_ocr
        self.ocr_paths: list[str] = []
        self.release_load = threading.Event()
        self.release_load.set()

    def _default_ocr(self, request: httpx.Request) -> httpx.Response:
        doc_id = request.url.path.removeprefix("/ocr/documents/")
        if doc_id.startswith("paper-"):
            document = load_ocr_fixture().model_copy(update={"doc_id": doc_id})
            return httpx.Response(200, content=document.model_dump_json())
        return httpx.Response(
            404, json=OcrDocumentError(code=OcrDocumentErrorCode.NOT_FOUND, doc_id=doc_id).model_dump(mode="json")
        )

    def _ocr(self, request: httpx.Request) -> httpx.Response:
        self.ocr_paths.append(request.url.path)
        return self.ocr_handler(request)

    def _load_tts(self) -> FakeTts:
        self.release_load.wait(timeout=5)
        return self.tts

    def app(self):
        app = create_app(
            config=self.config,
            manifest=self.manifest,
            tts_loader=self._load_tts,
            stt_loader=lambda: self.stt,
            exit_process=self.exit_recorder,
            ocr_transport=httpx.MockTransport(self._ocr),
        )
        self.tts.gate = app.state.services.gate
        return app


@pytest.fixture
def env(tmp_path: Path, exit_recorder: ExitRecorder) -> Env:
    return Env(tmp_path, exit_recorder)


@pytest.fixture
def client(env: Env) -> Iterator[TestClient]:
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        wait_ready(c)
        yield c


def wait_ready(c: TestClient) -> None:
    for _ in range(500):
        if c.get("/health").json()["ready"]:
            return
        time.sleep(0.01)
    raise AssertionError("models did not load")


def decoded_seconds(mp3: bytes) -> float:
    decoded, rate = sf.read(io.BytesIO(mp3))
    assert rate == FAKE_SAMPLE_RATE and decoded.ndim == 1
    return len(decoded) / rate


def spoken_seconds(env: "Env") -> float:
    return sum(len(ph) for ph in env.tts.synthesize_calls) * SAMPLES_PER_PHONEME / FAKE_SAMPLE_RATE


def wait_render(c: TestClient, url: str, sections: int) -> dict:
    for _ in range(500):
        body = c.get(url).json()
        if not body["active"] and len(body["sections"]) >= sections:
            return body
        time.sleep(0.01)
    raise AssertionError("render did not finish")


def test_health_while_loading_then_ready(env: Env) -> None:
    env.release_load.clear()
    with TestClient(env.app()) as c:
        loading = c.get("/health").json()
        assert loading["status"] == "ok" and loading["ready"] is False
        assert loading["tts_loaded"] is False and loading["stt_loaded"] is False
        assert loading["models"]["tts"] == {"repo_id": "hexgrad/Kokoro-82M", "revision": "rev-tts"}
        env.release_load.set()
        wait_ready(c)
        ready = c.get("/health").json()
        assert ready["ready"] and ready["tts_loaded"] and ready["stt_loaded"]


def test_503_model_loading_on_every_gpu_route(env: Env) -> None:
    env.release_load.clear()
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        c.post(f"/v1/papers/{DOC}/script")
        for response in (
            c.post("/v1/speech", json={"text": "hi"}),
            c.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [1]}),
            c.post("/v1/transcriptions", content=b"x", headers={"content-type": "audio/wav"}),
            c.get(f"/v1/papers/{DOC}/sections/1/stream"),
        ):
            assert response.status_code == 503, response.text
            assert response.json()["code"] == "model_loading"
        env.release_load.set()


def test_prepare_created_unchanged_rebuilt(client: TestClient, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    first = client.post(f"/v1/papers/{DOC}/script")
    assert first.status_code == 200
    body = first.json()
    assert body["outcome"] == "created" and len(body["script"]["sections"]) == 5
    assert "text" not in body["script"]["sections"][0]
    assert body["script"]["sections"][3]["speakable"] is False

    assert client.post(f"/v1/papers/{DOC}/script").json()["outcome"] == "unchanged"

    changed = load_ocr_fixture()
    changed.pages[0].blocks[0].text = "Different author"
    env.ocr_handler = lambda r: httpx.Response(200, content=changed.model_dump_json())
    assert client.post(f"/v1/papers/{DOC}/script").json()["outcome"] == "rebuilt"

    monkeypatch.setattr("voice_service.api.routes_papers.SCRIPT_BUILDER_VERSION", 99)
    assert client.post(f"/v1/papers/{DOC}/script").json()["outcome"] == "rebuilt"


def test_prepare_error_mapping(client: TestClient, env: Env) -> None:
    assert client.post("/v1/papers/missing/script").json() == {
        "code": "ocr_document_not_found",
        "message": "OCR service has no stored document for 'missing'",
    }
    env.ocr_handler = lambda r: httpx.Response(500)
    assert client.post(f"/v1/papers/{DOC}/script").status_code == 502

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("t", request=request)

    env.ocr_handler = timeout
    timed_out = client.post(f"/v1/papers/{DOC}/script")
    assert timed_out.status_code == 504 and timed_out.json()["code"] == "ocr_timeout"

    env.ocr_handler = lambda r: httpx.Response(200, json={"doc_id": DOC})
    assert client.post(f"/v1/papers/{DOC}/script").json()["code"] == "ocr_contract_violation"

    bad = load_ocr_fixture()
    bad.pages[0].blocks[0].ref = "margin_note"
    env.ocr_handler = lambda r: httpx.Response(200, content=bad.model_dump_json())
    unknown = client.post(f"/v1/papers/{DOC}/script")
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_block_ref"
    assert "margin_note" in unknown.json()["message"] and "page 1" in unknown.json()["message"]


def test_script_409_then_full_script_and_listing(client: TestClient) -> None:
    missing = client.get(f"/v1/papers/{DOC}/script")
    assert missing.status_code == 409 and missing.json()["code"] == "script_not_prepared"
    assert client.get("/v1/papers").json() == []

    client.post(f"/v1/papers/{DOC}/script")
    script = client.get(f"/v1/papers/{DOC}/script").json()
    assert script["sections"][2]["segments"][1]["text"] == "We measure things carefully."
    listing = client.get("/v1/papers").json()
    assert listing[0]["doc_id"] == DOC and listing[0]["section_count"] == 5


def test_section_stream_decodes_to_the_full_spoken_duration(client: TestClient, env: Env) -> None:
    env.tts.max_phonemes = 10  # forces several back-to-back windows inside the body block
    client.post(f"/v1/papers/{DOC}/script")
    response = client.get(f"/v1/papers/{DOC}/sections/2/stream")
    assert response.status_code == 200 and response.headers["content-type"] == "audio/mpeg"
    assert len(response.headers["X-Voice-Render-Key"]) == 64
    assert len(env.tts.synthesize_calls) >= 3 and env.tts.synthesize_calls[0] == "Methods"
    expected = spoken_seconds(env) + SECTION_2_PAUSE_SECONDS
    assert abs(decoded_seconds(response.content) - expected) <= DURATION_TOLERANCE_SECONDS


def test_section_stream_errors(client: TestClient) -> None:
    assert client.get(f"/v1/papers/{DOC}/sections/1/stream").json()["code"] == "script_not_prepared"
    client.post(f"/v1/papers/{DOC}/script")
    assert client.get(f"/v1/papers/{DOC}/sections/99/stream").json()["code"] == "section_not_found"
    not_speakable = client.get(f"/v1/papers/{DOC}/sections/3/stream")
    assert not_speakable.status_code == 422 and not_speakable.json()["code"] == "section_not_speakable"


def test_first_window_failure_is_a_5xx(client: TestClient, env: Env) -> None:
    client.post(f"/v1/papers/{DOC}/script")
    env.tts.fail_on = lambda ph: True
    response = client.get(f"/v1/papers/{DOC}/sections/2/stream")
    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "message": "internal server error"}
    assert "Traceback" not in response.text
    env.tts.fail_on = None
    assert client.get(f"/v1/papers/{DOC}/sections/2/stream").status_code == 200  # slot was released


def test_first_window_failure_after_a_leading_omitted_block_is_still_a_5xx(client: TestClient, env: Env) -> None:
    client.post(f"/v1/papers/{DOC}/script")
    store = client.app.state.services.store
    script = store.load_script(DOC)
    script.sections[2].omitted.append(OmittedBlock(page_number=1, block_index=0, ref="table"))
    store.save_script(script)
    env.tts.fail_on = lambda ph: True
    response = client.get(f"/v1/papers/{DOC}/sections/2/stream")
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    env.tts.fail_on = None
    assert client.get(f"/v1/papers/{DOC}/sections/2/stream").status_code == 200  # slot was released


def test_free_text_speech(client: TestClient) -> None:
    response = client.post("/v1/speech", json={"text": "Hello there."})
    assert response.status_code == 200 and response.headers["content-type"] == "audio/mpeg"
    assert decoded_seconds(response.content) > 0
    assert client.post("/v1/speech", json={"text": ""}).status_code == 422
    too_long = client.post("/v1/speech", json={"text": "x" * 200_001})
    assert too_long.status_code == 422 and too_long.json()["code"] == "request_validation_failed"
    assert "xxxx" not in too_long.text  # request input is never echoed back


def test_long_speech_decodes_to_the_full_duration_across_many_windows(client: TestClient, env: Env) -> None:
    response = client.post("/v1/speech", json={"text": "aaaa " * 3000})
    assert response.status_code == 200
    assert len(env.tts.synthesize_calls) >= 3
    assert abs(decoded_seconds(response.content) - spoken_seconds(env)) <= DURATION_TOLERANCE_SECONDS
    assert spoken_seconds(env) > 4  # long enough that a truncated (first-chunk-only) body would fail


def test_speech_with_nothing_speakable_is_422(client: TestClient) -> None:
    response = client.post("/v1/speech", json={"text": "~~~"})
    assert response.status_code == 422 and response.json()["code"] == "nothing_to_speak"


def test_render_submit_status_download_and_playlist(client: TestClient) -> None:
    client.post(f"/v1/papers/{DOC}/script")
    submitted = client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [2, 4]})
    assert submitted.status_code == 202
    key = submitted.json()["render_key"]
    url = f"/v1/papers/{DOC}/renders/{key}"

    status = wait_render(client, url, 2)
    assert [s["index"] for s in status["sections"]] == [2, 4]
    assert all(s["status"] == "rendered" and s["download_url"] for s in status["sections"])

    mp3 = client.get(status["sections"][0]["download_url"])
    assert mp3.status_code == 200 and mp3.headers["content-type"] == "audio/mpeg"
    assert abs(decoded_seconds(mp3.content) - status["sections"][0]["audio_seconds"]) <= DURATION_TOLERANCE_SECONDS

    playlist = client.get(f"{url}/playlist.m3u")
    assert playlist.headers["content-type"].startswith("audio/x-mpegurl")
    lines = playlist.text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1].endswith(",Methods") and lines[2] == "sections/2.mp3"
    assert lines[3].endswith(",Results") and lines[4] == "sections/4.mp3"


def test_render_errors(client: TestClient, env: Env) -> None:
    assert (
        client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [1]}).json()["code"] == "script_not_prepared"
    )
    client.post(f"/v1/papers/{DOC}/script")
    assert (
        client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [99]}).json()["code"] == "section_not_found"
    )
    assert (
        client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [3]}).json()["code"]
        == "section_not_speakable"
    )
    assert client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": []}).status_code == 422
    assert client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [1, 1]}).status_code == 422
    absent = "0" * 64
    assert client.get(f"/v1/papers/{DOC}/renders/{absent}").json()["code"] == "render_not_found"
    assert client.get(f"/v1/papers/{DOC}/renders/{absent}/playlist.m3u").json()["code"] == "render_not_found"
    assert client.get(f"/v1/papers/{DOC}/renders/{absent}/sections/1.mp3").json()["code"] == "section_not_rendered"


@pytest.mark.parametrize("bad_key", ["..x", "A" * 64, "abc", "g" * 64])
def test_malformed_render_key_is_a_422_on_every_render_route(client: TestClient, bad_key: str) -> None:
    for suffix in ("", "/playlist.m3u", "/sections/1.mp3"):
        response = client.get(f"/v1/papers/{DOC}/renders/{bad_key}{suffix}")
        assert response.status_code == 422 and response.json()["code"] == "request_validation_failed"


def test_playlist_of_a_stale_render_is_409(client: TestClient, env: Env) -> None:
    client.post(f"/v1/papers/{DOC}/script")
    key = client.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [2]}).json()["render_key"]
    url = f"/v1/papers/{DOC}/renders/{key}"
    wait_render(client, url, 1)
    assert client.get(f"{url}/playlist.m3u").status_code == 200

    changed = load_ocr_fixture()
    changed.pages[0].blocks[0].text = "Different author"
    env.ocr_handler = lambda r: httpx.Response(200, content=changed.model_dump_json())
    assert client.post(f"/v1/papers/{DOC}/script").json()["outcome"] == "rebuilt"

    stale = client.get(f"{url}/playlist.m3u")
    assert stale.status_code == 409 and stale.json()["code"] == "render_stale"


def test_render_queue_full_is_429(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    env = Env(tmp_path, exit_recorder, VOICE_RENDER_QUEUE_MAX=1)
    release = threading.Event()
    original = env.tts.synthesize

    def blocking(phonemes: str):
        release.wait(timeout=5)
        return original(phonemes)

    env.tts.synthesize = blocking  # type: ignore[method-assign]
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        wait_ready(c)
        for doc in ("paper-1", "paper-2", "paper-3"):
            c.post(f"/v1/papers/{doc}/script")
        assert c.post("/v1/papers/paper-1/renders", json={"section_indices": [1]}).status_code == 202
        time.sleep(0.3)  # the worker picks paper-1 up and blocks inside synthesize
        queued = c.post("/v1/papers/paper-2/renders", json={"section_indices": [1]})
        assert queued.status_code == 202 and queued.json()["queued_position"] == 0
        full = c.post("/v1/papers/paper-3/renders", json={"section_indices": [1]})
        assert full.status_code == 429 and full.json()["code"] == "render_queue_full"
        release.set()


def test_same_render_resubmitted_while_active_is_merged_not_queued(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    env = Env(tmp_path, exit_recorder, VOICE_RENDER_QUEUE_MAX=1)
    release = threading.Event()
    original = env.tts.synthesize
    env.tts.synthesize = lambda ph: (release.wait(timeout=5), original(ph))[1]  # type: ignore[method-assign]
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        wait_ready(c)
        c.post(f"/v1/papers/{DOC}/script")
        first = c.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [1]}).json()
        again = c.post(f"/v1/papers/{DOC}/renders", json={"section_indices": [2]})
        assert again.status_code == 202 and again.json()["render_key"] == first["render_key"]
        assert again.json()["requested"] == [1, 2]
        release.set()


def test_stream_slots_exhausted_is_429(tmp_path: Path, exit_recorder: ExitRecorder) -> None:
    env = Env(tmp_path, exit_recorder, VOICE_MAX_ACTIVE_STREAMS=1)
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        wait_ready(c)
        services = c.app.state.services
        assert services.streams.try_acquire()  # an in-flight stream holds the only slot
        response = c.post("/v1/speech", json={"text": "hello"})
        assert response.status_code == 429 and response.json()["code"] == "too_many_streams"
        services.streams.release()
        assert c.post("/v1/speech", json={"text": "hello"}).status_code == 200


def test_transcription_happy_path(client: TestClient, env: Env) -> None:
    response = client.post(
        "/v1/transcriptions", content=b"audio-bytes", headers={"content-type": "audio/mp4"}, params={"language": "de"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "hello world" and body["language"] == "de" and body["duration_seconds"] == 1.5
    assert body["segments"] == [{"start": 0.0, "end": 1.5, "text": "hello world"}]
    assert body["model"] == {"repo_id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "revision": "rev-stt"}
    assert env.stt.calls[0][1] == "de" and not env.stt.calls[0][0].exists()  # temp file removed


def test_transcription_language_absent_means_autodetect(client: TestClient, env: Env) -> None:
    client.post("/v1/transcriptions", content=b"x", headers={"content-type": "video/webm; codecs=opus"})
    assert env.stt.calls[0][1] is None


def _spool_files() -> list[Path]:
    return list(Path(tempfile.gettempdir()).glob("voice_stt_*"))


def test_transcription_media_type_and_language_rejections(client: TestClient, env: Env) -> None:
    unsupported = client.post("/v1/transcriptions", content=b"x", headers={"content-type": "text/plain"})
    assert unsupported.status_code == 415 and unsupported.json()["code"] == "unsupported_media_type"
    missing = client.post("/v1/transcriptions", content=b"x")
    assert missing.status_code == 415 and missing.json()["code"] == "unsupported_media_type"

    bad_language = client.post(
        "/v1/transcriptions", content=b"x", headers={"content-type": "audio/wav"}, params={"language": "xx"}
    )
    assert bad_language.status_code == 422 and bad_language.json()["code"] == "unsupported_language"

    undecodable = client.post("/v1/transcriptions", content=UNDECODABLE_MARKER, headers={"content-type": "audio/wav"})
    assert undecodable.status_code == 422 and undecodable.json()["code"] == "audio_undecodable"
    assert env.stt.calls[-1][1] is None and _spool_files() == []


def test_declared_oversize_is_413_before_any_byte_is_read(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("voice_service.api.routes_stt.MAX_TRANSCRIPTION_UPLOAD_BYTES", 10)

    async def must_not_read(request: object) -> Path:
        raise AssertionError("the body was read although Content-Length exceeded the cap")

    monkeypatch.setattr("voice_service.api.routes_stt._spool_request", must_not_read)
    big = client.post("/v1/transcriptions", content=b"x" * 11, headers={"content-type": "audio/wav"})
    assert big.status_code == 413 and big.json()["code"] == "upload_too_large"
    assert MAX_TRANSCRIPTION_UPLOAD_BYTES == 100 * 1024 * 1024
    assert _spool_files() == []


def test_streamed_oversize_without_content_length_is_413_and_leaves_no_spool_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("voice_service.api.routes_stt.MAX_TRANSCRIPTION_UPLOAD_BYTES", 10)

    def body() -> Iterator[bytes]:
        yield b"x" * 6
        yield b"x" * 6

    big = client.post("/v1/transcriptions", content=body(), headers={"content-type": "audio/wav"})
    assert big.status_code == 413 and big.json()["code"] == "upload_too_large"
    assert _spool_files() == []


@pytest.mark.parametrize("declared", ["abc", "-5", "1.5", ""])
def test_invalid_content_length_is_400(client: TestClient, declared: str) -> None:
    response = client.post(
        "/v1/transcriptions", content=b"x", headers={"content-type": "audio/wav", "content-length": declared}
    )
    assert response.status_code == 400 and response.json()["code"] == "invalid_content_length"
    assert _spool_files() == []


def test_transcription_slots_exhausted_is_429(env: Env) -> None:
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        wait_ready(c)
        limiter = c.app.state.services.transcriptions
        assert limiter.try_acquire() and limiter.try_acquire()
        response = c.post("/v1/transcriptions", content=b"x", headers={"content-type": "audio/wav"})
        assert response.status_code == 429 and response.json()["code"] == "too_many_transcriptions"


async def _call_and_disconnect(app: object, path: str) -> None:
    """Drive the ASGI app directly with a client that disconnects before the body is sent."""

    async def receive() -> dict[str, str]:
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        await asyncio.sleep(0)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "root_path": "",
        "server": ("test", 80),
        "client": ("peer", 1),
    }
    await app(scope, receive, send)  # type: ignore[operator]


def test_clients_disconnecting_before_the_body_do_not_leak_stream_slots(env: Env) -> None:
    with TestClient(env.app(), raise_server_exceptions=False) as c:
        wait_ready(c)
        c.post(f"/v1/papers/{DOC}/script")
        slots = env.config.max_active_streams
        for _ in range(slots + 1):
            c.portal.call(_call_and_disconnect, c.app, f"/v1/papers/{DOC}/sections/2/stream")
        assert c.get(f"/v1/papers/{DOC}/sections/2/stream").status_code == 200  # not 429


def test_unknown_route_uses_error_body(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404 and set(response.json()) == {"code", "message"}


def test_invalid_doc_id_in_path_is_422(client: TestClient) -> None:
    response = client.get("/v1/papers/has%20space/script")
    assert response.status_code == 422 and response.json()["code"] == "request_validation_failed"
