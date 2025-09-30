"""
AWS ElastiCache Redis integration service.

This module provides functionality for connecting to ElastiCache Redis clusters
with connection pooling, error handling, and automatic failover support.
"""

import logging
from typing import Any, Dict, List, Optional, Union

import redis
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

logger = logging.getLogger(__name__)


class ElastiCacheError(Exception):
    """Exception raised for ElastiCache operations."""

    pass


class ElastiCacheManager:
    """
    ElastiCache Redis connection manager with pooling and error handling.
    
    Provides high-level Redis operations with automatic connection management,
    pooling, and error recovery for ElastiCache clusters.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        max_connections: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
    ):
        """
        Initialize ElastiCache manager.
        
        Args:
            host: Redis host (ElastiCache endpoint)
            port: Redis port
            password: Redis password (AUTH token)
            db: Redis database number
            max_connections: Maximum connections in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            retry_on_timeout: Whether to retry on timeout
            health_check_interval: Health check interval in seconds
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval
        
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._redis: Optional[aioredis.Redis] = None

    async def _ensure_connection(self) -> aioredis.Redis:
        """Ensure Redis connection is established."""
        if self._redis is None:
            try:
                # Create connection pool
                self._pool = aioredis.ConnectionPool(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    db=self.db,
                    max_connections=self.max_connections,
                    socket_timeout=self.socket_timeout,
                    socket_connect_timeout=self.socket_connect_timeout,
                    retry_on_timeout=self.retry_on_timeout,
                    health_check_interval=self.health_check_interval,
                )
                
                # Create Redis client
                self._redis = aioredis.Redis(connection_pool=self._pool)
                
                # Test connection
                await self._redis.ping()
                logger.info(f"Successfully connected to Redis at {self.host}:{self.port}")
                
            except Exception as e:
                logger.error(f"Failed to connect to Redis at {self.host}:{self.port}: {e}")
                raise ElastiCacheError(f"Failed to connect to Redis: {e}") from e
        
        return self._redis

    async def ping(self) -> bool:
        """
        Test Redis connection.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            redis_client = await self._ensure_connection()
            result = await redis_client.ping()
            return result is True
        except Exception as e:
            logger.warning(f"Redis ping failed: {e}")
            return False

    async def get(self, key: str) -> Optional[str]:
        """
        Get value from Redis.
        
        Args:
            key: Redis key
            
        Returns:
            Value as string, or None if key doesn't exist
            
        Raises:
            ElastiCacheError: If operation fails
        """
        try:
            redis_client = await self._ensure_connection()
            value = await redis_client.get(key)
            return value.decode("utf-8") if value else None
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error getting key {key}: {e}")
            raise ElastiCacheError(f"Connection error: {e}") from e
        except RedisError as e:
            logger.error(f"Redis error getting key {key}: {e}")
            raise ElastiCacheError(f"Redis error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error getting key {key}: {e}")
            raise ElastiCacheError(f"Unexpected error: {e}") from e

    async def set(
        self, 
        key: str, 
        value: str, 
        ex: Optional[int] = None, 
        nx: bool = False
    ) -> bool:
        """
        Set value in Redis.
        
        Args:
            key: Redis key
            value: Value to set
            ex: Expiration time in seconds
            nx: Only set if key doesn't exist
            
        Returns:
            True if operation succeeded
            
        Raises:
            ElastiCacheError: If operation fails
        """
        try:
            redis_client = await self._ensure_connection()
            result = await redis_client.set(key, value, ex=ex, nx=nx)
            return result is True
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error setting key {key}: {e}")
            raise ElastiCacheError(f"Connection error: {e}") from e
        except RedisError as e:
            logger.error(f"Redis error setting key {key}: {e}")
            raise ElastiCacheError(f"Redis error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error setting key {key}: {e}")
            raise ElastiCacheError(f"Unexpected error: {e}") from e

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from Redis.
        
        Args:
            keys: Keys to delete
            
        Returns:
            Number of keys deleted
            
        Raises:
            ElastiCacheError: If operation fails
        """
        try:
            redis_client = await self._ensure_connection()
            return await redis_client.delete(*keys)
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error deleting keys {keys}: {e}")
            raise ElastiCacheError(f"Connection error: {e}") from e
        except RedisError as e:
            logger.error(f"Redis error deleting keys {keys}: {e}")
            raise ElastiCacheError(f"Redis error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error deleting keys {keys}: {e}")
            raise ElastiCacheError(f"Unexpected error: {e}") from e

    async def exists(self, *keys: str) -> int:
        """
        Check if keys exist in Redis.
        
        Args:
            keys: Keys to check
            
        Returns:
            Number of existing keys
            
        Raises:
            ElastiCacheError: If operation fails
        """
        try:
            redis_client = await self._ensure_connection()
            return await redis_client.exists(*keys)
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error checking keys {keys}: {e}")
            raise ElastiCacheError(f"Connection error: {e}") from e
        except RedisError as e:
            logger.error(f"Redis error checking keys {keys}: {e}")
            raise ElastiCacheError(f"Redis error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error checking keys {keys}: {e}")
            raise ElastiCacheError(f"Unexpected error: {e}") from e

    async def get_info(self) -> Dict[str, Any]:
        """
        Get Redis server information.
        
        Returns:
            Dictionary with Redis server info
            
        Raises:
            ElastiCacheError: If operation fails
        """
        try:
            redis_client = await self._ensure_connection()
            info = await redis_client.info()
            
            # Extract key metrics
            return {
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory"),
                "used_memory_human": info.get("used_memory_human"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),
            }
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error getting info: {e}")
            raise ElastiCacheError(f"Connection error: {e}") from e
        except RedisError as e:
            logger.error(f"Redis error getting info: {e}")
            raise ElastiCacheError(f"Redis error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error getting info: {e}")
            raise ElastiCacheError(f"Unexpected error: {e}") from e

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self._redis:
            try:
                await self._redis.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._redis = None
                self._pool = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()