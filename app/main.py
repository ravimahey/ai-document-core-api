from fastapi import FastAPI
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException,app_exception_handler

settings = get_settings()


def create_app():
    app = FastAPI()
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    def health():
        return {"status": "OK"}

    app.add_exception_handler(
        AppException,
        app_exception_handler,
)

    return app


app = create_app()
