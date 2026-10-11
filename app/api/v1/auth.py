from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AuthServiceDep
from app.schemas.auth import Token

auth_router = APIRouter(tags=["Auth APIs"])


@auth_router.post("/token", response_model=Token)
def login(
    auth: AuthServiceDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    return auth.login(form_data.username, form_data.password)
