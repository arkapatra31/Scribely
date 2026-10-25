"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from scribely import __version__
from scribely.api.ws import register_ws
from scribely.config import Settings
from scribely.models import HealthResponse
from scribely.session import LiveSessionManager


def create_app(settings: Settings, live: LiveSessionManager) -> FastAPI:

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        live.warm_up()
        yield
        await live.shutdown()

    app = FastAPI(title="Scribely backend", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.live = live

    @app.get("/health")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    register_ws(app, live, settings.server.allowed_origins)
    return app
