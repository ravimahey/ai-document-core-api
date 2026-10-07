from app.schemas.auth import LoginForm
from app.services.user import UserService
from app.schemas.auth import Token

class AuthService:
    def __init__(self, user_service: UserService):
        self._user_service = user_service

    def login(self, login_form: LoginForm):
        is_valid_user = self._user_service.get_user_by_email(login_form.email)
        token = Token( access_token="123123", token_type="barear")
        return token
    # def _generate_token():

