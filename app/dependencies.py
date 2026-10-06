from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db.session_factory() as session:
        yield session

