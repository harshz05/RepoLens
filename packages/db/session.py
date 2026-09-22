import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from packages.db.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./repolens_dev.db")

# If sqlite, set connect_args
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db() -> None:
    """Initialize database tables and vector extensions if PostgreSQL."""
    async with engine.begin() as conn:
        if "postgresql" in DATABASE_URL:
            try:
                from sqlalchemy import text
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            except Exception:
                pass
        await conn.run_sync(Base.metadata.create_all)

        # Ensure SQLite has newly added columns if existing DB file was present
        if "sqlite" in DATABASE_URL:
            from sqlalchemy import text
            for col_stmt in [
                "ALTER TABLE repository_versions ADD COLUMN embedding_model VARCHAR(100);",
                "ALTER TABLE repository_versions ADD COLUMN embedding_dimension INTEGER;",
                "ALTER TABLE code_chunks ADD COLUMN symbol_fqn TEXT;",
                "ALTER TABLE code_chunks ADD COLUMN language VARCHAR(50) DEFAULT '';",
                "ALTER TABLE code_chunks ADD COLUMN embedding_model VARCHAR(100);",
                "ALTER TABLE code_chunks ADD COLUMN embedding_dimension INTEGER;",
                "ALTER TABLE code_chunks ADD COLUMN embedding TEXT;",
            ]:
                try:
                    await conn.execute(text(col_stmt))
                except Exception:
                    pass

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
