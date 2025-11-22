import os, json
from typing import Optional
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

API_KEY = os.getenv("API_KEY", "local-llm")
UPSTREAM_BASE_URL = os.getenv("UPSTREAM_BASE_URL", "http://llm:8000/v1")

app = FastAPI(title="LLM Gateway", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

def _auth_ok(request: Request) -> bool:
    bearer = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    xkey = request.headers.get("x-api-key", "").strip()
    return bearer == API_KEY or xkey == API_KEY

@app.get("/v1/models")
async def models(request: Request):
    if not _auth_ok(request):
        raise HTTPException(status_code=401, detail="Invalid API key")
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.get(f"{UPSTREAM_BASE_URL}/models")
        return JSONResponse(r.json(), status_code=r.status_code)

async def _proxy_json(request: Request, path: str):
    if not _auth_ok(request):
        raise HTTPException(status_code=401, detail="Invalid API key")
    body = await request.body()
    headers = {"Content-Type": "application/json"}
    stream = False
    try:
        payload = json.loads(body.decode() or "{}")
        stream = bool(payload.get("stream", False))
    except Exception:
        pass
    async with httpx.AsyncClient(timeout=None) as client:
        if stream:
            async def gen():
                async with client.stream("POST", f"{UPSTREAM_BASE_URL}{path}", content=body, headers=headers) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
            return StreamingResponse(gen(), media_type="text/event-stream")
        else:
            r = await client.post(f"{UPSTREAM_BASE_URL}{path}", content=body, headers=headers)
            return JSONResponse(r.json(), status_code=r.status_code)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    return await _proxy_json(request, "/chat/completions")

@app.post("/v1/completions")
async def completions(request: Request):
    return await _proxy_json(request, "/completions")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
