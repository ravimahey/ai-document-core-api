from fastapi import APIRouter

from app.api.v1.auth import auth_router
from app.api.v1.chat import chat_router
from app.api.v1.document import document_router
from app.api.v1.user import user_router

api_router = APIRouter()
api_router.include_router(user_router)
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(document_router)
