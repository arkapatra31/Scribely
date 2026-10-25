"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from scribely import __version__
from scribely.config import Settings
from scribely.models import HealthResponse


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Scribely backend", version=__version__)
    app.state.settings = settings

    @app.get("/health")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    return app
