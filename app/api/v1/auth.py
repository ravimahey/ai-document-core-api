from fastapi import APIRouter, HTTPException, Depends
from app.api.deps import AuthServiceDep
from app.schemas.auth import Token, LoginForm
from app.services.auth import AuthService
from starlette import status
from typing import Annotated
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm


auth_router = APIRouter(tags=["Auth APIs"])


@auth_router.post("/token", response_model=Token)
def login(auth: AuthServiceDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    token = auth.login(form_data.username, form_data.password)
    return token
