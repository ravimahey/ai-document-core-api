from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings


def build_engine(database_url: str, echo: bool = False) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    # check_same_thread=False is required because FastAPI runs sync endpoints in a threadpool.
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    engine = create_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_settings = get_settings()
engine = build_engine(_settings.database_url, _settings.db_echo)

# autoflush=False: flushes happen explicitly in repositories, so behavior is predictable.
# expire_on_commit=False: objects stay readable after commit (needed to serialize responses).
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
