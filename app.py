"""
Public HTTPS Q&A endpoint for the Acme Appliances order ledger exam.

POST {"question": "..."} -> {"answer": ...}
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ledger import STORE
from qa import answer_question


@asynccontextmanager
async def lifespan(_: Starlette):
    STORE.load()
    yield


async def ask(request: Request) -> JSONResponse:
    if not STORE.ready:
        return JSONResponse(
            {"error": STORE.error or "Ledger not loaded"},
            status_code=503,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if not isinstance(body, dict) or "question" not in body:
        return JSONResponse(
            {"error": 'Expected JSON body {"question": "..."}'},
            status_code=400,
        )

    question = body["question"]
    if not isinstance(question, str) or not question.strip():
        return JSONResponse({"error": "question must be a non-empty string"}, status_code=400)

    try:
        result = answer_question(question)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse({"answer": result})


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok" if STORE.ready else "loading",
            "ready": STORE.ready,
            "orders_loaded": len(STORE.orders),
            "error": STORE.error,
            "ask_endpoint": "/ask",
        }
    )


routes = [
    Route("/ask", ask, methods=["POST"]),
    Route("/", ask, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
    Route("/", health, methods=["GET"]),
]

app = Starlette(routes=routes, lifespan=lifespan)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
