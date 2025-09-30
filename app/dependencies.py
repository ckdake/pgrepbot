"""
Dependency injection for FastAPI
"""

import os

import redis.asyncio as redis
from fastapi import HTTPException, status

# Global Redis client
_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    """Get Redis client dependency"""
    global _redis_client

    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)

        try:
            await _redis_client.ping()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Redis connection failed: {str(e)}",
            ) from e

    return _redis_client


async def close_redis_client():
    """Close Redis client"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
