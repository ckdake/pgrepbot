"""
Background task management service
"""

import asyncio
import logging
from typing import Any

import redis.asyncio as redis

from app.services.alerting import AlertingService
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background tasks for the application"""

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.tasks: dict[str, asyncio.Task] = {}
        self.running = False

        # Initialize services
        from app.services.aws_rds import RDSClient
        from app.services.aws_secrets import SecretsManagerClient

        secrets_client = SecretsManagerClient()
        rds_client = RDSClient()

        self.connection_manager = PostgreSQLConnectionManager(secrets_client=secrets_client, rds_client=rds_client)
        self.replication_service = ReplicationDiscoveryService(self.connection_manager, redis_client)
        self.alerting_service = AlertingService(redis_client, self.connection_manager, self.replication_service)

    async def start_all_tasks(self) -> None:
        """Start all background tasks"""
        if self.running:
            logger.warning("Background tasks already running")
            return

        self.running = True
        logger.info("Starting background tasks")

        try:
            # Start monitoring task
            self.tasks["monitoring"] = asyncio.create_task(self._run_monitoring_task(), name="monitoring_task")

            # Start health check task
            self.tasks["health_check"] = asyncio.create_task(self._run_health_check_task(), name="health_check_task")

            # Start cleanup task
            self.tasks["cleanup"] = asyncio.create_task(self._run_cleanup_task(), name="cleanup_task")

            logger.info(f"Started {len(self.tasks)} background tasks")

        except Exception as e:
            logger.error(f"Failed to start background tasks: {e}")
            await self.stop_all_tasks()
            raise

    async def stop_all_tasks(self) -> None:
        """Stop all background tasks"""
        if not self.running:
            return

        self.running = False
        logger.info("Stopping background tasks")

        # Cancel all tasks
        for task_name, task in self.tasks.items():
            if not task.done():
                logger.info(f"Cancelling task: {task_name}")
                task.cancel()

        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        self.tasks.clear()
        logger.info("All background tasks stopped")

    async def _run_monitoring_task(self) -> None:
        """Run continuous monitoring"""
        logger.info("Starting monitoring task")

        # Initialize default thresholds
        await self.alerting_service.initialize_default_thresholds()

        while self.running:
            try:
                await self.alerting_service.run_monitoring_cycle()
                await asyncio.sleep(60)  # Run every minute
            except asyncio.CancelledError:
                logger.info("Monitoring task cancelled")
                break
            except Exception as e:
                logger.error(f"Monitoring task error: {e}")
                await asyncio.sleep(60)  # Continue after error

    async def _run_health_check_task(self) -> None:
        """Run periodic health checks"""
        logger.info("Starting health check task")

        while self.running:
            try:
                # Check database connections
                await self._check_database_health()

                # Check Redis connection
                await self._check_redis_health()

                await asyncio.sleep(300)  # Run every 5 minutes
            except asyncio.CancelledError:
                logger.info("Health check task cancelled")
                break
            except Exception as e:
                logger.error(f"Health check task error: {e}")
                await asyncio.sleep(300)

    async def _run_cleanup_task(self) -> None:
        """Run periodic cleanup of old data"""
        logger.info("Starting cleanup task")

        while self.running:
            try:
                await self._cleanup_old_alerts()
                await self._cleanup_old_metrics()

                await asyncio.sleep(3600)  # Run every hour
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
                await asyncio.sleep(3600)

    async def _check_database_health(self) -> None:
        """Check health of all configured databases"""
        try:
            from app.models.database import DatabaseConfig

            db_configs = await DatabaseConfig.get_all_from_redis(self.redis_client)

            for db_config in db_configs:
                try:
                    health = self.connection_manager.get_health_status(db_config.id)
                    if not health.is_healthy:
                        logger.warning(f"Database {db_config.id} is unhealthy: {health.error_message}")
                except Exception as e:
                    logger.error(f"Failed to check health for database {db_config.id}: {e}")

        except Exception as e:
            logger.error(f"Failed to check database health: {e}")

    async def _check_redis_health(self) -> None:
        """Check Redis connection health"""
        try:
            await self.redis_client.ping()
            logger.debug("Redis health check passed")
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

    async def _cleanup_old_alerts(self) -> None:
        """Clean up old resolved alerts"""
        try:
            from datetime import datetime, timedelta

            from app.models.alerts import Alert, AlertStatus

            # Keep resolved alerts for 30 days
            cutoff_date = datetime.utcnow() - timedelta(days=30)

            all_alerts = await Alert.get_all_from_redis(self.redis_client)
            cleaned_count = 0

            for alert in all_alerts:
                if alert.status == AlertStatus.RESOLVED and alert.resolved_at and alert.resolved_at < cutoff_date:
                    await Alert.delete_from_redis(self.redis_client, alert.id)
                    cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} old resolved alerts")

        except Exception as e:
            logger.error(f"Failed to cleanup old alerts: {e}")

    async def _cleanup_old_metrics(self) -> None:
        """Clean up old metric data"""
        try:
            # Clean up old metric keys from Redis
            # This is a placeholder - in a real implementation, you might want to
            # store metrics in a time-series database or implement proper TTL

            pattern = "metrics:*"
            keys = await self.redis_client.keys(pattern)

            # For now, just log the count
            if keys:
                logger.debug(f"Found {len(keys)} metric keys in Redis")

        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")

    def get_task_status(self) -> dict[str, Any]:
        """Get status of all background tasks"""
        status = {
            "running": self.running,
            "tasks": {},
        }

        for task_name, task in self.tasks.items():
            status["tasks"][task_name] = {
                "name": task.get_name(),
                "done": task.done(),
                "cancelled": task.cancelled(),
            }

            if task.done() and not task.cancelled():
                try:
                    exception = task.exception()
                    if exception:
                        status["tasks"][task_name]["error"] = str(exception)
                except Exception:
                    pass

        return status


# Global instance
_background_manager: BackgroundTaskManager | None = None


async def get_background_manager(redis_client: redis.Redis) -> BackgroundTaskManager:
    """Get or create background task manager"""
    global _background_manager

    if _background_manager is None:
        _background_manager = BackgroundTaskManager(redis_client)

    return _background_manager


async def start_background_tasks(redis_client: redis.Redis) -> None:
    """Start background tasks (called at application startup)"""
    manager = await get_background_manager(redis_client)
    await manager.start_all_tasks()


async def stop_background_tasks() -> None:
    """Stop background tasks (called at application shutdown)"""
    global _background_manager

    if _background_manager:
        await _background_manager.stop_all_tasks()
        _background_manager = None
