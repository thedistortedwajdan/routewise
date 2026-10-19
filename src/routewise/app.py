"""FastAPI app exposing an OpenAI-compatible endpoint."""

from __future__ import annotations

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import load_settings
from .gateway import BudgetExceeded, Gateway
from .ledger import Ledger
from .translate import UnsupportedRequest


def _error(status: int, message: str, kind: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": kind}}, status_code=status)


def create_app(gateway: Gateway | None = None) -> FastAPI:
    app = FastAPI(title="routewise")
    if gateway is None:
        settings = load_settings()
        gateway = Gateway(settings, Ledger(settings.db_path), anthropic.AsyncAnthropic())
    app.state.gateway = gateway

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/v1/stats")
    async def stats():
        return app.state.gateway.ledger.summary()

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        try:
            body = await request.json()
        except ValueError:
            return _error(400, "invalid JSON body", "invalid_request_error")
        try:
            return await app.state.gateway.complete(body)
        except UnsupportedRequest as e:
            return _error(400, str(e), "invalid_request_error")
        except BudgetExceeded as e:
            return _error(429, str(e), "budget_exceeded")
        except anthropic.APIStatusError as e:
            status = e.status_code if e.status_code >= 400 else 502
            return _error(status, e.message, "upstream_error")
        except anthropic.APIConnectionError as e:
            return _error(502, f"upstream connection error: {e}", "upstream_error")

    return app
