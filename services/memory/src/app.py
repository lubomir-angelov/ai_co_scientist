# main.py
from fastapi import FastAPI
from .routers import episodes, queries

app = FastAPI(title="Octo Memory Service", version="0.1.0")

app.include_router(episodes.router, prefix="/v1/memory")
app.include_router(queries.router, prefix="/v1/memory")
