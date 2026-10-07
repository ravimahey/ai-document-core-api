from fastapi import APIRouter, HTTPException
from app.api.deps import AuthServiceDep
from app.schemas.auth import Token, LoginForm
from app.services.auth import AuthService
from starlette import status


auth_router = APIRouter()


@auth_router.get("/login", response_model=Token)
def login(auth: AuthServiceDep, login_form: LoginForm):
    token = auth.login(login_form=login_form)
    return token