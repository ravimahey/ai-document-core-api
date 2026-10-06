from fastapi import APIRouter
from .v1.user import user_router

api_router = APIRouter()
api_router.include_router(user_router)
