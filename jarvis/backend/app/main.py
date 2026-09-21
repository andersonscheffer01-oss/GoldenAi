from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from .config import ROOT_DIR, get_settings
from .database import init_db
from .routers import advanced_finance, auth, chat, devices, finance, frontend, health, jarvis_commands, pc_commands, pluggy_finance, professional_finance, receipts, uploads
from .services.alert_service import check_alerts
from .database import SessionLocal
from .logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    task = None
    if settings.alerts_enabled:
        async def alert_loop():
            while True:
                try:
                    with SessionLocal() as db: check_alerts(db)
                except Exception:
                    pass
                await asyncio.sleep(settings.alert_check_interval_seconds)
        task = asyncio.create_task(alert_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        description="Fundacao independente do Golden Jarvis.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def production_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(Exception)
    async def safe_error_handler(_request: Request, _exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "Erro interno. Consulte os logs do servidor."})

    frontend_assets = ROOT_DIR / "frontend" / "assets"
    if frontend_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_assets)), name="assets")

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(uploads.router)
    app.include_router(chat.router)
    app.include_router(receipts.router)
    app.include_router(finance.router)
    app.include_router(finance.receipt_router)
    app.include_router(advanced_finance.router)
    app.include_router(professional_finance.router)
    app.include_router(jarvis_commands.router)
    app.include_router(devices.router)
    app.include_router(pc_commands.router)
    app.include_router(pluggy_finance.router)
    app.include_router(frontend.router)
    return app


app = create_app()
