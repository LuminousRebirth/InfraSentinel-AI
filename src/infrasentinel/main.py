from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .api import router as health_router
from .config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    app.include_router(health_router, prefix=settings.api_prefix)
    return app


app = create_app()
