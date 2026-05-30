import logging
from typing import Optional, Set
import redis.asyncio as aioredis
from app.config.settings import settings

logger = logging.getLogger("orbitchat.cache")

class CacheService:
    """
    Enterprise Redis Cluster Interface.
    Manages user presence heartbeats, distributed pub/sub routing, 
    and atomic distributed Sequence ID generation.
    """
    def __init__(self):
        # Initialize an un-allocated Redis client variable
        self.client: Optional[aioredis.Redis] = None

    def initialize(self):
        """
        Warms up the connection pool to the Redis backend instance.
        Called exactly once during application startup.
        """
        logger.info("Connecting to high-performance Redis cache cluster...")
        self.client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,          # Automatically converts bytes to Python strings
            max_connections=100,            # Capped connection pool size for microservice scaling
            socket_timeout=5.0
        )

    async def close(self):
        """
        Gracefully disconnects and drains the connection pool on shutdown.
        """
        if self.client:
            await self.client.close()
            logger.info("Redis cache cluster pool gracefully drained.")

    # =========================================================================
    # PRESENCE SYSTEM (Bitmap / KV Tracking)
    # =========================================================================

    async def set_user_online(self, user_id: int, heartbeat_seconds: int = 60) -> None:
        """
        Marks a user as active/online using an atomic Key-Value pair with a TTL (Time-To-Live).
        The WebSocket connection must continuously refresh this before it expires.
        """
        key = f"presence:user:{user_id}"
        # Set string value to 'online' and enforce auto-expiration
        await self.client.set(key, "online", ex=heartbeat_seconds)

    async def set_user_offline(self, user_id: int) -> None:
        """
        Explicitly removes a user's online state when they close their connection.
        """
        key = f"presence:user:{user_id}"
        await self.client.delete(key)

    async def is_user_online(self, user_id: int) -> bool:
        """
        Checks instantly in-memory if a specific user is currently active.
        """
        key = f"presence:user:{user_id}"
        exists = await self.client.exists(key)
        return bool(exists)

    # =========================================================================
    # ATOMIC LOCAL SEQUENCE ID ENGINE
    # =========================================================================

    async def generate_next_sequence_id(self, channel_id: int) -> int:
        """
        Generates a continuous, gapless, strictly increasing 64-bit integer 
        for a specific chat room. Guarantees safety under massive concurrency.
        """
        key = f"sequence:channel:{channel_id}"
        # INCR is an atomic operation inside Redis single-threaded execution model
        next_id = await self.client.incr(key)
        return next_id

# Instantiate a global singleton to be shared across the application nodes
cache_service = CacheService()