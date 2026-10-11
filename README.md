# AI Document SaaS Core (`ai-document-saas-core`)

Backend API service for AI-powered document analysis, authentication, and conversational AI. Built with FastAPI, SQLAlchemy 2, Alembic, LangChain, and Pydantic v2.

---

## Architecture Overview

```mermaid
flowchart TD
    Client["Client / Frontend UI (/chat)"] --> API["API Routers (FastAPI)"]
    API --> Deps["Dependencies & DI Layer"]
    Deps --> Services["Services (UserService, AuthService, OTPService, ChatService, DocumentService)"]
    Services --> Repos["Repositories (UserRepository, OTPRepository, ChatRepository, DocumentRepository)"]
    Repos --> DB[("Database (SQLite / PostgreSQL)")]
    
    Services -.-> Security["Core Security (bcrypt, HMAC-SHA256, PyJWT)"]
    Services -.-> Storage["Object Storage (MinIO / S3 / Local)"]
    Services -.-> Celery["Celery Task Queue (Redis Broker)"]
    Celery -.-> Worker["Document Worker (LangChain, OpenAI Embeddings)"]
    Worker -.-> FAISS[("FAISS Vector Stores (User Isolated)")]
    Worker -.-> DB
```

The application adheres to a clean layered architecture:
- **API Layer (`app/api/`)**: Route handlers, multipart upload streaming, parameter validation, and dependency injection.
- **Service Layer (`app/services/`)**: Business logic, cryptographic operations, storage abstractions, FAISS index management, and LangChain LLM orchestration.
- **Background Tasks (`app/tasks/`)**: Celery tasks for asynchronous document extraction, chunking, and embedding.
- **Repository Layer (`app/repositories/`)**: Database query abstractions.
- **Models (`app/models/`)**: SQLAlchemy declarative ORM models (`User`, `OTPChallenge`, `Conversation`, `Message`, `Document`).
- **Schemas (`app/schemas/`)**: Pydantic DTOs for request/response serialization.
- **Core (`app/core/`)**: Settings, security utilities, exception classes, and logging.

---

## Features

### 1. Document Upload & Ingestion (MinIO / S3, Celery, LangChain, FAISS)
- **Object Storage Abstraction**: Works seamlessly with MinIO (local dev) and AWS S3 (production) using a unified `boto3` client with bucket auto-initialization.
- **Streaming Uploads**: Streams multi-part uploads directly without loading entire multi-megabyte files into RAM, enforcing strict size limits (default 25 MB) and verifying SHA-256 checksums.
- **Asynchronous Processing**: Upload endpoints return `202 Accepted` immediately, offloading heavy parsing, chunking, and embedding to Celery workers backed by Redis.
- **Document Extractors**: Native parsing of `.pdf` (pypdf), `.docx` (docx2txt), `.txt`, and `.md` via LangChain document loaders.
- **Recursive Chunking & Embeddings**: Splits documents using `RecursiveCharacterTextSplitter` and embeds with OpenAI `text-embedding-3-small`.
- **User-Isolated FAISS Vector Stores**: Persists FAISS indexes in separate per-user directories protected by cross-platform filesystem locking, preventing race conditions.
- **Lifecycle & Cleanup**: Deleting a document removes the object from storage, purges the vectors from the user's FAISS index, and deletes database metadata.
- **Retry Mechanism**: Resilient recovery for failed ingestion jobs via a dedicated retry endpoint with exponential backoff on transient errors.

### 2. Conversational AI Chatbot (LangChain & OpenAI)
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

### Document Management APIs (Protected: Bearer Token)

| Method | Endpoint | Status | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/documents` | `202 Accepted` | Upload document (`.pdf`, `.docx`, `.txt`, `.md`), store in MinIO/S3, enqueue background processing |
| `GET` | `/api/v1/documents` | `200 OK` | Paginated list of user's uploaded documents (`status`, `page`, `page_size`) |
| `GET` | `/api/v1/documents/{id}` | `200 OK` | Retrieve document metadata, chunk count, and processing status |
| `DELETE` | `/api/v1/documents/{id}` | `204 No Content` | Delete document from database, remove storage file, purge FAISS vector embeddings |
| `POST` | `/api/v1/documents/{id}/retry` | `202 Accepted` | Re-enqueue background processing for a failed document |

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

# OpenAI / LangChain Configuration
OPENAI_API_KEY="sk-..."                 # OpenAI API Key from platform.openai.com
OPENAI_MODEL="gpt-4.1-nano"             # Cheapest suitable model (e.g., gpt-4.1-nano, gpt-4o-mini)
OPENAI_TEMPERATURE=0.7                  # Generation temperature (0.0 to 1.0)
OPENAI_MAX_OUTPUT_TOKENS=2048           # Max response token budget
CHAT_MAX_INPUT_CHARACTERS=4000          # Per-message character limit
CHAT_HISTORY_MESSAGE_LIMIT=20           # Context-window recent message limit
CHAT_REQUEST_TIMEOUT_SECONDS=30.0       # Timeout for AI provider invocation
CHAT_SYSTEM_PROMPT="You are a helpful, respectful, and concise AI assistant."

# Object Storage Configuration (MinIO / S3 / Local)
OBJECT_STORAGE_PROVIDER="minio"         # Options: minio, s3, local
MINIO_ENDPOINT_URL="http://localhost:9000"
MINIO_ACCESS_KEY="minioadmin"
MINIO_SECRET_KEY="minioadmin"
MINIO_BUCKET_NAME="documents"
MINIO_REGION="us-east-1"
MINIO_SECURE=false

# AWS S3 (when OBJECT_STORAGE_PROVIDER=s3)
# AWS_ACCESS_KEY_ID=""
# AWS_SECRET_ACCESS_KEY=""
# AWS_REGION="us-east-1"
# AWS_S3_BUCKET_NAME="my-production-bucket"

# Local Storage Fallback (when OBJECT_STORAGE_PROVIDER=local)
LOCAL_STORAGE_PATH="./data/storage"

# Celery & Redis Task Queue
CELERY_BROKER_URL="redis://localhost:6379/0"
CELERY_RESULT_BACKEND="redis://localhost:6379/1"
CELERY_TASK_ALWAYS_EAGER=false          # Set true for testing synchronous execution without Redis

# Document Ingestion & Embeddings
MAX_UPLOAD_SIZE_BYTES=26214400          # 25 MB max upload limit
EMBEDDING_MODEL="text-embedding-3-small"
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
FAISS_INDEX_DIR="./data/faiss_indexes"
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

## Infrastructure Setup (MinIO, Redis & Celery)

### 1. Start MinIO Object Storage (Local Development)

Using Docker:

```bash
docker run -d -p 9000:9000 -p 9001:9001 --name minio \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"
```
The bucket configured in `MINIO_BUCKET_NAME` (default `documents`) is automatically verified and created by the storage service upon first use.

### 2. Start Redis Broker

Using Docker:

```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

### 3. Start Celery Background Worker

Start the Celery worker process to consume document processing tasks:

- **Linux / macOS**:
  ```bash
  uv run celery -A app.tasks.celery_app worker --loglevel=info
  ```

- **Windows**:
  ```powershell
  uv run celery -A app.tasks.celery_app worker --loglevel=info -P solo
  ```
  *(Note: The `-P solo` pool flag prevents Win32 multiprocessing spawn conflicts on Windows).*

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
