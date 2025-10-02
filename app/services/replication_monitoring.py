"""
Replication monitoring background service.

This module provides background tasks for continuous monitoring of replication
streams using APScheduler.
"""

import logging
from datetime import datetime
from typing import Any

import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.replication import ReplicationStream
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService

logger = logging.getLogger(__name__)


class ReplicationMonitoringService:
    """Service for continuous monitoring of replication streams."""

    def __init__(
        self,
        connection_manager: PostgreSQLConnectionManager,
        redis_client: redis.Redis,
        rds_client: Any = None,
    ):
        """Initialize the replication monitoring service."""
        self.connection_manager = connection_manager
        self.redis_client = redis_client
        self.rds_client = rds_client
        self.scheduler = AsyncIOScheduler()
        self.discovery_service = ReplicationDiscoveryService(
            connection_manager=connection_manager,
            rds_client=rds_client,
        )

    async def start_monitoring(self) -> None:
        """Start the background monitoring tasks."""
        try:
            logger.info("Starting replication monitoring service")

            # Schedule metrics collection every 30 seconds
            self.scheduler.add_job(
                self._collect_all_metrics,
                "interval",
                seconds=30,
                id="collect_metrics",
                replace_existing=True,
            )

            # Schedule stream health checks every 2 minutes
            self.scheduler.add_job(
                self._check_stream_health,
                "interval",
                minutes=2,
                id="health_check",
                replace_existing=True,
            )

            # Schedule cache cleanup every 10 minutes
            self.scheduler.add_job(
                self._cleanup_expired_cache,
                "interval",
                minutes=10,
                id="cache_cleanup",
                replace_existing=True,
            )

            self.scheduler.start()
            logger.info("Replication monitoring service started successfully")

        except Exception as e:
            logger.error(f"Failed to start replication monitoring service: {e}")
            raise

    async def stop_monitoring(self) -> None:
        """Stop the background monitoring tasks."""
        try:
            logger.info("Stopping replication monitoring service")
            self.scheduler.shutdown(wait=True)
            logger.info("Replication monitoring service stopped")
        except Exception as e:
            logger.error(f"Failed to stop replication monitoring service: {e}")

    async def _collect_all_metrics(self) -> None:
        """Collect metrics for all cached replication streams."""
        try:
            logger.debug("Collecting metrics for all replication streams")

            # Get all cached streams
            streams = await self._get_cached_streams()
            if not streams:
                logger.debug("No cached streams found for metrics collection")
                return

            metrics_collected = 0
            for stream in streams:
                try:
                    # Collect metrics for this stream
                    metrics = await self.discovery_service.collect_replication_metrics(stream)

                    # Cache the metrics with TTL
                    await self._cache_stream_metrics(stream.id, metrics)
                    metrics_collected += 1

                except Exception as e:
                    logger.warning(f"Failed to collect metrics for stream {stream.id}: {e}")
                    # Cache error state
                    await self._cache_stream_error(stream.id, str(e))

            logger.debug(f"Collected metrics for {metrics_collected}/{len(streams)} streams")

        except Exception as e:
            logger.error(f"Failed to collect all metrics: {e}")

    async def _check_stream_health(self) -> None:
        """Check health status of all replication streams."""
        try:
            logger.debug("Checking health of all replication streams")

            streams = await self._get_cached_streams()
            if not streams:
                return

            healthy_count = 0
            for stream in streams:
                try:
                    # Check if stream is still active
                    is_healthy = await self._check_single_stream_health(stream)

                    # Update health status in cache
                    await self._cache_stream_health(stream.id, is_healthy)

                    if is_healthy:
                        healthy_count += 1

                except Exception as e:
                    logger.warning(f"Failed to check health for stream {stream.id}: {e}")
                    await self._cache_stream_health(stream.id, False)

            logger.debug(f"Health check complete: {healthy_count}/{len(streams)} streams healthy")

        except Exception as e:
            logger.error(f"Failed to check stream health: {e}")

    async def _cleanup_expired_cache(self) -> None:
        """Clean up expired cache entries."""
        try:
            logger.debug("Cleaning up expired cache entries")

            # Get all replication stream keys
            pattern = "replication_stream:*"
            keys = await self.redis_client.keys(pattern)

            expired_count = 0
            for key in keys:
                try:
                    # Check if key has TTL
                    ttl = await self.redis_client.ttl(key)
                    if ttl == -1:  # No TTL set, set one
                        await self.redis_client.expire(key, 3600)  # 1 hour
                    elif ttl == -2:  # Key doesn't exist
                        expired_count += 1

                except Exception as e:
                    logger.warning(f"Failed to check TTL for key {key}: {e}")

            # Clean up metrics cache older than 1 hour
            metrics_pattern = "stream_metrics:*"
            metrics_keys = await self.redis_client.keys(metrics_pattern)

            for key in metrics_keys:
                try:
                    ttl = await self.redis_client.ttl(key)
                    if ttl == -2:  # Expired
                        expired_count += 1

                except Exception as e:
                    logger.warning(f"Failed to check metrics TTL for key {key}: {e}")

            if expired_count > 0:
                logger.debug(f"Cleaned up {expired_count} expired cache entries")

        except Exception as e:
            logger.error(f"Failed to cleanup expired cache: {e}")

    async def _get_cached_streams(self) -> list[ReplicationStream]:
        """Get all cached replication streams."""
        try:
            pattern = "replication_stream:*"
            keys = await self.redis_client.keys(pattern)

            streams = []
            for key in keys:
                try:
                    data = await self.redis_client.get(key)
                    if data:
                        stream = ReplicationStream.model_validate_json(data)
                        streams.append(stream)
                except Exception as e:
                    logger.warning(f"Failed to parse cached stream from key {key}: {e}")

            return streams

        except Exception as e:
            logger.error(f"Failed to get cached streams: {e}")
            return []

    async def _check_single_stream_health(self, stream: ReplicationStream) -> bool:
        """Check if a single replication stream is healthy."""
        try:
            if stream.type == "logical":
                # Check if subscription is still active
                query = """
                SELECT subname, subenabled
                FROM pg_subscription
                WHERE subname = $1
                """
                result = await self.connection_manager.execute_query(
                    stream.target_db_id, query, stream.subscription_name
                )
                return len(result) > 0 and result[0]["subenabled"]

            elif stream.type == "physical":
                # Check if replication slot is still active
                query = """
                SELECT slot_name, active
                FROM pg_replication_slots
                WHERE slot_name = $1
                """
                result = await self.connection_manager.execute_query(
                    stream.source_db_id, query, stream.replication_slot_name
                )
                return len(result) > 0 and result[0]["active"]

            return False

        except Exception as e:
            logger.warning(f"Failed to check health for stream {stream.id}: {e}")
            return False

    async def _cache_stream_metrics(self, stream_id: str, metrics: Any) -> None:
        """Cache stream metrics with TTL."""
        try:
            key = f"stream_metrics:{stream_id}"
            value = {
                "lag_bytes": metrics.lag_bytes,
                "lag_seconds": metrics.lag_seconds,
                "wal_position": metrics.wal_position,
                "synced_tables": metrics.synced_tables,
                "total_tables": metrics.total_tables,
                "collected_at": datetime.utcnow().isoformat(),
            }
            # Cache for 5 minutes
            await self.redis_client.setex(key, 300, str(value))
            logger.debug(f"Cached metrics for stream {stream_id}")

        except Exception as e:
            logger.warning(f"Failed to cache metrics for stream {stream_id}: {e}")

    async def _cache_stream_error(self, stream_id: str, error_message: str) -> None:
        """Cache stream error state."""
        try:
            key = f"stream_error:{stream_id}"
            value = {
                "error_message": error_message,
                "error_time": datetime.utcnow().isoformat(),
            }
            # Cache for 10 minutes
            await self.redis_client.setex(key, 600, str(value))
            logger.debug(f"Cached error for stream {stream_id}")

        except Exception as e:
            logger.warning(f"Failed to cache error for stream {stream_id}: {e}")

    async def _cache_stream_health(self, stream_id: str, is_healthy: bool) -> None:
        """Cache stream health status."""
        try:
            key = f"stream_health:{stream_id}"
            value = {
                "is_healthy": is_healthy,
                "checked_at": datetime.utcnow().isoformat(),
            }
            # Cache for 5 minutes
            await self.redis_client.setex(key, 300, str(value))
            logger.debug(f"Cached health status for stream {stream_id}: {is_healthy}")

        except Exception as e:
            logger.warning(f"Failed to cache health for stream {stream_id}: {e}")


# Global monitoring service instance
_monitoring_service: ReplicationMonitoringService | None = None


async def get_monitoring_service(
    connection_manager: PostgreSQLConnectionManager,
    redis_client: redis.Redis,
    rds_client: Any = None,
) -> ReplicationMonitoringService:
    """Get or create the global monitoring service instance."""
    global _monitoring_service

    if _monitoring_service is None:
        _monitoring_service = ReplicationMonitoringService(
            connection_manager=connection_manager,
            redis_client=redis_client,
            rds_client=rds_client,
        )
        await _monitoring_service.start_monitoring()

    return _monitoring_service


async def stop_monitoring_service() -> None:
    """Stop the global monitoring service."""
    global _monitoring_service

    if _monitoring_service is not None:
        await _monitoring_service.stop_monitoring()
        _monitoring_service = None
