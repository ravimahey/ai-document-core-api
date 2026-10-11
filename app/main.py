from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException, app_exception_handler
from app.core.logging_config import setup_logging

settings = get_settings()


def create_app() -> FastAPI:
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "OK", "app": settings.app_name}

    @app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
    def chat_ui() -> FileResponse:
        html_file = Path(__file__).resolve().parent / "static" / "chat.html"
        return FileResponse(html_file)

    app.add_exception_handler(
        AppException,
        app_exception_handler,  # type: ignore[arg-type]
    )

    return app


app = create_app()
