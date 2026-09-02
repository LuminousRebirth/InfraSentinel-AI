from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from .api import router as health_router
from .config import get_settings
from .detection_api import router as detection_router
from .errors import install_error_handlers
from .identity_api import router as identity_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    install_error_handlers(app)

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(identity_router, prefix=settings.api_prefix)
    app.include_router(detection_router, prefix=settings.api_prefix)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    @app.get("/", include_in_schema=False)
    def index():
        index_file = frontend_dist / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return RedirectResponse(url="/docs")

    @app.get("/{path:path}", include_in_schema=False)
    def web_ui(path: str) -> FileResponse:
        if path.startswith(("api/", "docs", "redoc")):
            raise HTTPException(status_code=404)
        index_file = frontend_dist / "index.html"
        if not index_file.is_file():
            raise HTTPException(status_code=404)
        candidate = (frontend_dist / path).resolve()
        if candidate.is_relative_to(frontend_dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)

    return app


app = create_app()
