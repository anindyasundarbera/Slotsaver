from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .db import Base, dispose_engines, get_engine
from .deps import reset_factory
from .errors import AppError
from .api import (
    assistant_routes,
    auth_routes,
    booking_routes,
    meta_routes,
    owner_routes,
    webhook_routes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("slotsaver")

SENSITIVE = ("authorization", "cookie", "set-cookie", "paypal-auth", "x-csrf-token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    if settings.seed_demo_data:
        from .db import make_session_factory
        from .seed import seed_database
        from sqlalchemy import select
        from .models import DemoClock

        factory = make_session_factory(engine)
        with factory() as db:
            if db.execute(select(DemoClock)).scalar_one_or_none() is None:
                log.info("seeding demo dataset")
                seed_database(db, settings)
                db.commit()
    log.info(
        "startup complete mode=paypal:%s assistant:%s db=%s",
        settings.paypal_mode,
        settings.assistant_mode,
        settings.database_url.split("///")[-1],
    )
    yield
    dispose_engines()


def _find_spa_dist() -> Path | None:
    """Locate a built SPA, tolerating the different layouts Angular can emit."""
    root = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "frontend"
    for candidate in (root / "browser", root):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="SlotSaver API",
        version=meta_routes.VERSION,
        description="AI booking and PayPal Sandbox payment POC for a fictional appliance-repair business.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    @app.middleware("http")
    async def correlation_and_logging(request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:16]
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith("/api/health"):
            log.info(
                "%s %s -> %s %.1fms cid=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                correlation_id,
            )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        body = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "correlation_id": getattr(request.state, "correlation_id", ""),
                "details": exc.details,
            }
        }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The request did not match the expected schema.",
                    "correlation_id": getattr(request.state, "correlation_id", ""),
                    "details": {
                        "fields": [
                            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "")}
                            for e in exc.errors()[:8]
                        ]
                    },
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                    "correlation_id": getattr(request.state, "correlation_id", ""),
                    "details": {},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        log.exception("unhandled error cid=%s", getattr(request.state, "correlation_id", ""))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong. Quote the correlation id when reporting it.",
                    "correlation_id": getattr(request.state, "correlation_id", ""),
                    "details": {},
                }
            },
        )

    for router in (
        meta_routes.router,
        auth_routes.router,
        booking_routes.router,
        assistant_routes.router,
        owner_routes.router,
        webhook_routes.router,
    ):
        app.include_router(router)

    # Same-origin by default: no CORS relaxation in the demo path.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    dist = _find_spa_dist()
    if dist is not None:
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"error": {"code": "NOT_FOUND", "message": "No such route."}}, 404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":  # pragma: no cover
    main()
