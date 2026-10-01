# Voice service

Listen to papers and dictate to the co-scientist.

- **TTS**: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) reads a paper (rendered to MP3
  files, or streamed) or arbitrary text.
- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `large-v3-turbo`
  (`int8_float16`) transcribes phone voice memos.

Port `8007`. GPU only (CUDA, no CPU path). Models are pinned in `model_pins.json` and baked into
the image at build time; the runtime is offline (`HF_HUB_OFFLINE=1`).

## Workflow: prepare, then render or stream

1. **Prepare** (needs the OCR service up): `POST /v1/papers/{doc_id}/script` fetches the stored OCR
   document (`GET /ocr/documents/{doc_id}` on the OCR service) and builds a **script**: logical
   sections opened by heading blocks, tables / figures / display equations / captions omitted by
   their OCR block type, HTML markup stripped (`<sup>` becomes Unicode superscripts), inline LaTeX
   converted to Unicode. Citation numbers are spoken as written (see Known limitations). The script is stored in voice; preparing again is idempotent (`unchanged`).
2. **Choose sections**: `GET /v1/papers/{doc_id}/script` lists every section with its full text.
   `references` and the like are not auto-detected: you pick the section indices to hear.
3. **Render or stream** (needs only voice; OCR may be down): `POST .../renders` renders chosen
   sections to MP3 files (queued, resumable, idempotent), `GET .../sections/{index}/stream`
   streams one section immediately.

```bash
make -C services/voice up
make -C services/voice health                      # "ready": true once both models are loaded
make -C services/voice prepare DOC_ID=arxiv:2410.12345
curl -s localhost:8007/v1/papers/arxiv:2410.12345/script | jq '.sections[] | {index, heading, speakable}'
make -C services/voice render DOC_ID=arxiv:2410.12345 SECTIONS='1 2 3'
curl -s localhost:8007/v1/papers/arxiv:2410.12345/renders/<render_key>          # status
curl -s localhost:8007/v1/papers/arxiv:2410.12345/renders/<render_key>/playlist.m3u
curl -sO localhost:8007/v1/papers/arxiv:2410.12345/renders/<render_key>/sections/2.mp3
curl -s localhost:8007/v1/papers/arxiv:2410.12345/sections/2/stream > section2.mp3
curl -s -X POST localhost:8007/v1/speech -H 'Content-Type: application/json' \
  -d '{"text":"Hello from the co-scientist."}' > hello.mp3
curl -s --data-binary @memo.m4a -H 'Content-Type: audio/mp4' 'localhost:8007/v1/transcriptions?language=en'
```

Doc ids are the OCR doc ids (`DocId`: no `/`, no whitespace).

## API

| Method and path | Purpose |
|---|---|
| `GET /health` | `{status, service, ready, tts_loaded, stt_loaded, models}`; answers while models load |
| `POST /v1/papers/{doc_id}/script` | prepare the script: `created`, `rebuilt` or `unchanged` |
| `GET /v1/papers` | prepared papers |
| `GET /v1/papers/{doc_id}/script` | the full script (every segment's full text) |
| `GET /v1/papers/{doc_id}/sections/{index}/stream` | chunked `audio/mpeg`; header `X-Voice-Render-Key` |
| `POST /v1/papers/{doc_id}/renders` | `{"section_indices": [...]}` -> 202 render status |
| `GET /v1/papers/{doc_id}/renders/{render_key}` | status, queue position, per-section records |
| `GET /v1/papers/{doc_id}/renders/{render_key}/sections/{index}.mp3` | download |
| `GET /v1/papers/{doc_id}/renders/{render_key}/playlist.m3u` | M3U of the rendered sections; `409 render_stale` once the paper's script was re-prepared with different content |
| `POST /v1/speech` | free text -> chunked `audio/mpeg` |
| `POST /v1/transcriptions?language=<code>` | raw audio body (`Content-Type` `audio/*`, `video/webm` or `video/mp4`; not multipart) -> transcript; omit `language` to auto-detect |

Render keys are 64-char lowercase sha256 hex (anything else is a 422). The transcription upload is
bounded at 100 MiB: a larger `Content-Length` is a 413 before any byte is read, and a body without
one is counted as it streams. An unsupported `language` is a 422 `unsupported_language`.

Errors are `{"code", "message"}` (no stack traces). A stream starts at the first spoken window
(leading silence is not emitted) and that window is synthesized before
the response starts, so early failures are real 5xx responses; a failure mid-stream ends the
transfer incomplete (never padded with silence). Logs never contain paper, transcript or request
text.

Phone use: render the sections, then fetch the `.mp3` files or the playlist, or sync the
bind-mounted `data/voice/papers/<sha256(doc_id)>/renders/<render_key>/` directory.

## GPU tenancy

Voice co-resides with the llm on the single GPU: Kokoro fp32 (~0.35 GB) plus faster-whisper
`large-v3-turbo` `int8_float16` (~0.8 GB), one inference at a time (`GpuGate`). The budget is
**at most 3000 MiB** for the voice process (about 3.5 GiB is free next to the llm); the GPU smoke
test (`make test-gpu`) asserts it. Out-of-memory surfaces as a failed section or a 5xx, never
silently. A load failure or worker death exits the process (compose restarts it).

## Configuration

Every variable is required; an unset or empty one stops startup, naming it. See `.env.example`;
`compose.yaml` supplies the local-dev values. Only `core/config.py` reads the environment (guarded
by a fitness test).

## Known limitations

- OCR line-break hyphenation artifacts (`electro- optic`) are not repaired (needs lexical knowledge).
- Captions, tables, figures and display equations are omitted (an audible pause marks each gap);
  citation numbers are NOT stripped: OCR output carries no structural citation signal, and the
  characters inside `<sup>` and `[...]` are the same as in unit exponents (`cm⁻¹`), Miller indices
  (`[1, 1, 0]`) and intervals (`[0, 1]`), so they are spoken as written.
- English G2P only (baked); the voice id's first character selects American (`a`) or British (`b`).
- Each stream and each rendered section file is ONE continuous MP3 encoder session (streams write
  through an OS pipe so libsndfile emits no Xing/Info header; files carry a correct Info tag).
  Encoded chunks are never concatenated: independently encoded chunks would decode only up to the
  first one.
- Unpronounceable tokens are skipped and counted (`unspoken_tokens` in the render manifest).
- OCR documents cached before the `OCRResponse.pages` contract change must be re-OCR'd.

## Development

```bash
make -C services/voice install   # light venv: no torch / kokoro / faster-whisper
make -C services/voice test      # unit + architecture guards; GPU tests deselected
make -C services/voice lint
make -C services/voice pin-g2p   # re-record the spaCy wheel digest after changing the pinned wheel
make -C services/voice build     # pinned models are downloaded at build time
make -C services/voice test-gpu  # inside the running container: real models, VRAM budget
```

`model_pins.json` is the single source of truth for model identity (exact commit shas, STT
compute type, the spaCy `en_core_web_sm` wheel used by misaki). `g2p.sha256` is the digest recorded by
`make pin-g2p` (a unit test asserts the shipped pins are buildable).
