from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="claude-export-md API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
