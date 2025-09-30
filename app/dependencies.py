"""
Dependency injection for FastAPI
"""

import os

import redis.asyncio as redis
from fastapi import HTTPException, status

from app.services.aws_rds import RDSClient
from app.services.aws_secrets import SecretsManagerClient
from app.services.postgres_connection import PostgreSQLConnectionManager

# Global clients
_redis_client: redis.Redis | None = None
_connection_manager: PostgreSQLConnectionManager | None = None
_rds_client: RDSClient | None = None
_secrets_client: SecretsManagerClient | None = None


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


async def get_connection_manager() -> PostgreSQLConnectionManager:
    """Get PostgreSQL connection manager dependency"""
    global _connection_manager, _secrets_client, _rds_client

    if _connection_manager is None:
        # Initialize AWS clients if not already done
        if _secrets_client is None:
            _secrets_client = SecretsManagerClient()
        if _rds_client is None:
            _rds_client = RDSClient()

        _connection_manager = PostgreSQLConnectionManager(
            secrets_client=_secrets_client,
            rds_client=_rds_client,
        )

    return _connection_manager


async def get_rds_client() -> RDSClient:
    """Get RDS client dependency"""
    global _rds_client

    if _rds_client is None:
        _rds_client = RDSClient()

    return _rds_client


async def get_secrets_client() -> SecretsManagerClient:
    """Get Secrets Manager client dependency"""
    global _secrets_client

    if _secrets_client is None:
        _secrets_client = SecretsManagerClient()

    return _secrets_client


async def close_redis_client():
    """Close Redis client"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


async def close_connection_manager():
    """Close PostgreSQL connection manager"""
    global _connection_manager
    if _connection_manager:
        await _connection_manager.close_all()
        _connection_manager = None


async def close_all_clients():
    """Close all clients"""
    await close_redis_client()
    await close_connection_manager()
