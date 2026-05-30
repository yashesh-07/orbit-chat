import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config.settings import settings

# Setup structured industrial logging
logger = logging.getLogger("orbitchat.database")
logging.basicConfig(level=logging.INFO)

# Convert the standard Postgres connection string to an async-compatible URL
DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

logger.info("Initializing high-performance async database engine...")

# 1. Create the Async Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,                  
    pool_size=20,                # Maintain up to 20 persistent connections per node
    max_overflow=10,             # Allow up to 10 extra connections during traffic spikes
    pool_timeout=30,             
    pool_pre_ping=True           # Automatically check and recycle dead connections
)

# 2. Create the Async Session Factory
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False       
)

# 3. Establish the Declarative Base class for all data models
class Base(DeclarativeBase):
    pass

# 4. Dependency Injection Provider for FastAPI Routes
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency that yields an operational database session per request.
    Guarantees the connection is cleanly returned to the pool when finished.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit() # Atomic commit for successful requests
        except Exception as error:
            logger.error(f"Database transaction failure. Rolling back changes: {str(error)}")
            await session.rollback()
            raise
        finally:
            await session.close()