# AI Document SaaS Core (`ai-document-saas-core`)

Backend API service for AI-powered document analysis, authentication, and conversational AI. Built with FastAPI, SQLAlchemy 2, Alembic, LangChain, and Pydantic v2.

---

## Architecture Overview

```mermaid
flowchart TD
    Client["Client / Frontend UI (/chat)"] --> API["API Routers (FastAPI)"]
    API --> Deps["Dependencies & DI Layer"]
    Deps --> Services["Services (UserService, AuthService, OTPService, ChatService, LLMService)"]
    Services --> Repos["Repositories (UserRepository, OTPRepository, ChatRepository)"]
    Repos --> DB[("Database (SQLite / PostgreSQL)")]
    
    Services -.-> Security["Core Security (bcrypt, HMAC-SHA256, PyJWT)"]
    Services -.-> Config["Core Settings (Pydantic Settings)"]
    Services -.-> LangChain["LangChain OpenAI (ChatOpenAI)"]
```

The application adheres to a clean layered architecture:
- **API Layer (`app/api/`)**: Route handlers, parameter validation, and dependency injection.
- **Service Layer (`app/services/`)**: Business logic, cryptographic operations, LangChain LLM orchestration, and session state.
- **Repository Layer (`app/repositories/`)**: Database query abstractions.
- **Models (`app/models/`)**: SQLAlchemy declarative ORM models (`User`, `OTPChallenge`, `Conversation`, `Message`).
- **Schemas (`app/schemas/`)**: Pydantic DTOs for request/response serialization.
- **Core (`app/core/`)**: Settings, security utilities, exception classes, and logging.

---

## Features

### 1. Conversational AI Chatbot (LangChain & OpenAI)
- **ChatGPT-like Thread Management**: Create, list, paginate, continue, rename, and delete independent conversation threads.
- **Context Window Management**: Dynamically loads the most recent `N` messages (configurable via `CHAT_HISTORY_MESSAGE_LIMIT`) to maintain conversation context within cost and token limits.
- **Cheapest Suitable OpenAI Model**: Configured with `gpt-4.1-nano` (or `gpt-4o-mini`), fully customizable via the `OPENAI_MODEL` environment variable.
- **Zero Orphan Messages**: If OpenAI or network calls fail or time out, user messages are not left orphaned in the database, avoiding duplicate messages on retry.
- **User Data Isolation**: Strict ownership enforcement prevents any user from accessing, continuing, renaming, or deleting another user's conversation threads.
- **Interactive Web Interface**: A self-contained, responsive chat UI served at `/chat` featuring a conversation sidebar, auto-scroll, loading indicators, token metadata, and authentication integration.

### 2. User Authentication & Verification
- **Email OTP-based Registration**: Validates email and username uniqueness, hashes passwords immediately, delivers a 6-digit verification code, and activates the user account upon single-use verification.
- **Passwordless Email OTP Login**: Issues single-use login codes with anti-enumeration protection and returns standard RS256 JWT access tokens.
- **Password-Based OAuth2 Login**: Preserved for legacy and programmatic clients via `/api/v1/token`.

---

## API Endpoints Reference

### Chat & Conversation APIs (Protected: Bearer Token)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat/conversations` | Create a new conversation (optional initial message) |
| `GET` | `/api/v1/chat/conversations` | List user's conversations with pagination (`page`, `page_size`) |
| `GET` | `/api/v1/chat/conversations/{id}` | Retrieve conversation and its chronological message history |
| `PATCH` | `/api/v1/chat/conversations/{id}` | Rename conversation title |
| `DELETE` | `/api/v1/chat/conversations/{id}` | Delete conversation and cascade-delete messages |
| `POST` | `/api/v1/chat/conversations/{id}/messages` | Send message to conversation and receive AI assistant response |

### Web Interface & Health Check

| Method | Endpoint | Protected | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/chat` | No | Interactive single-page chatbot web application |
| `GET` | `/health` | No | System health check |

### Authentication & OTP APIs

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register/request-otp` | Request OTP for new user registration |
| `POST` | `/api/v1/auth/register/verify-otp` | Verify OTP and activate user account |
| `POST` | `/api/v1/auth/login/request-otp` | Request passwordless login OTP (anti-enumeration) |
| `POST` | `/api/v1/auth/login/verify-otp` | Verify login OTP and issue JWT access token |
| `POST` | `/api/v1/token` | Standard OAuth2 password login |

---

## Configuration & Environment Variables

Create or update your `.env` file from `.env.example`:

```env
DATABASE_URL="sqlite:///./data/app.db"

# JWT Settings (RS256 Asymmetric Keys)
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----...-----END RSA PRIVATE KEY-----"
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----...-----END PUBLIC KEY-----"
JWT_ISSUER="user"
JWT_AUDIENCE="user"
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# OTP Security Settings
OTP_EXPIRE_MINUTES=5
OTP_LENGTH=6
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN_SECONDS=60
OTP_MAX_REQUESTS_PER_HOUR=10
OTP_SECRET_KEY="replace-with-a-secure-random-secret-key"

# Email Delivery Configuration
EMAIL_PROVIDER="console" # Options: console, smtp, mock
SMTP_HOST="smtp.example.com"
SMTP_PORT=587
SMTP_USERNAME=""
SMTP_PASSWORD=""
SMTP_FROM_EMAIL="noreply@documentanalysis.ai"
SMTP_USE_TLS=true

# OpenAI / LangChain Chatbot Configuration
OPENAI_API_KEY="sk-..."                 # OpenAI API Key from platform.openai.com
OPENAI_MODEL="gpt-4.1-nano"             # Cheapest suitable model (e.g., gpt-4.1-nano, gpt-4o-mini)
OPENAI_TEMPERATURE=0.7                  # Generation temperature (0.0 to 1.0)
OPENAI_MAX_OUTPUT_TOKENS=2048           # Max response token budget
CHAT_MAX_INPUT_CHARACTERS=4000          # Per-message character limit
CHAT_HISTORY_MESSAGE_LIMIT=20           # Context-window recent message limit
CHAT_REQUEST_TIMEOUT_SECONDS=30.0       # Timeout for AI provider invocation
CHAT_SYSTEM_PROMPT="You are a helpful, respectful, and concise AI assistant."
```

### How to Obtain an OpenAI API Key
1. Sign up or log in at [platform.openai.com](https://platform.openai.com/).
2. Navigate to **API Keys** under your account settings.
3. Click **Create new secret key**, give it a name, and copy the `sk-...` token.
4. Set `OPENAI_API_KEY="sk-..."` in your `.env` file.

---

## Database Migrations

Apply Alembic migrations to update the database schema:

```bash
uv run alembic upgrade head
```

---

## Running the Application & Chatbot UI

Start the development server with Uvicorn:

```bash
uv run uvicorn app.main:app --reload
```

- **Interactive Chat Interface**: Open your browser at [http://127.0.0.1:8000/chat](http://127.0.0.1:8000/chat).
- **Swagger API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

---

## Automated Testing

Run the test suite:

```bash
uv run pytest -v
```
*(All tests use mock email and mock LangChain LLM fixtures; no real OpenAI API key or network calls are required to run automated tests).*
