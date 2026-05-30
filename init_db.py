import asyncio
import logging
from app.database.connection import engine, Base
from app.database import models  # Imperative: Imports models so SQLAlchemy discovers them

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orbitchat.init_db")

async def init_tables():
    logger.info("Connecting to database engine to provision schema layouts...")
    async with engine.begin() as conn:
        # Inspects Base and creates tables for all registered models
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schemas successfully provisioned on disk!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_tables())