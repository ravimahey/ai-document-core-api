from fastapi import APIRouter
from .v1.user import user_router
from .v1.auth import auth_router

from fastapi import Request
from fastapi.responses import JSONResponse

api_router = APIRouter()
api_router.include_router(user_router)
api_router.include_router(auth_router)
