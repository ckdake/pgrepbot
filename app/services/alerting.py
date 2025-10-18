"""
Alerting and monitoring service
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as redis

from app.models.alerts import (
    Alert,
    AlertMetric,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertThreshold,
    AlertType,
    NotificationChannel,
    SystemHealth,
)
from app.models.database import DatabaseConfig
from app.models.replication import ReplicationStream
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService

logger = logging.getLogger(__name__)


class AlertingService:
    """Service for managing alerts and monitoring"""

    def __init__(
        self,
        redis_client: redis.Redis,
        connection_manager: PostgreSQLConnectionManager,
        replication_service: ReplicationDiscoveryService,
    ):
        self.redis_client = redis_client
        self.connection_manager = connection_manager
        self.replication_service = replication_service
        self.start_time = time.time()
        
        # Default thresholds
        self._default_thresholds = [
            AlertThreshold(
                alert_type=AlertType.REPLICATION_LAG,
                severity=AlertSeverity.WARNING,
                metric_name="replication_lag_seconds",
                threshold_value=300.0,  # 5 minutes
                name="Replication Lag Warning",
                description="Alert when replication lag exceeds 5 minutes",
            ),
            AlertThreshold(
                alert_type=AlertType.REPLICATION_LAG,
                severity=AlertSeverity.CRITICAL,
                metric_name="replication_lag_seconds",
                threshold_value=1800.0,  # 30 minutes
                name="Replication Lag Critical",
                description="Alert when replication lag exceeds 30 minutes",
            ),
            AlertThreshold(
                alert_type=AlertType.DATABASE_CONNECTION,
                severity=AlertSeverity.CRITICAL,
                metric_name="database_connection_failed",
                threshold_value=1.0,
                comparison_operator="gte",
                name="Database Connection Failure",
                description="Alert when database connection fails",
            ),
            AlertThreshold(
                alert_type=AlertType.LONG_RUNNING_QUERY,
                severity=AlertSeverity.WARNING,
                metric_name="long_running_query_count",
                threshold_value=1.0,
                comparison_operator="gte",
                name="Long Running Queries Detected",
                description="Alert when queries run longer than 30 seconds",
            ),
            AlertThreshold(
                alert_type=AlertType.LONG_RUNNING_QUERY,
                severity=AlertSeverity.CRITICAL,
                metric_name="long_running_query_max_duration",
                threshold_value=300.0,  # 5 minutes
                comparison_operator="gte",
                name="Very Long Running Query",
                description="Alert when a query runs longer than 5 minutes",
            ),
        ]

    async def initialize_default_thresholds(self) -> None:
        """Initialize default alert thresholds if none exist"""
        try:
            existing_thresholds = await self.get_alert_thresholds()
            if not existing_thresholds:
                logger.info("Initializing default alert thresholds")
                for threshold in self._default_thresholds:
                    await threshold.save_to_redis(self.redis_client)
                logger.info(f"Created {len(self._default_thresholds)} default alert thresholds")
        except Exception as e:
            logger.error(f"Failed to initialize default thresholds: {e}")

    async def collect_metrics(self) -> list[AlertMetric]:
        """Collect system metrics for alerting"""
        metrics = []
        
        try:
            # Collect database health metrics
            db_configs = await self._get_database_configs()
            for db_config in db_configs:
                try:
                    health = self.connection_manager.get_health_status(db_config.id)
                    
                    # Database connection metric
                    connection_metric = AlertMetric(
                        metric_name="database_connection_failed",
                        metric_value=0.0 if health.is_healthy else 1.0,
                        database_id=db_config.id,
                        labels={"database_name": db_config.name, "role": db_config.role},
                    )
                    metrics.append(connection_metric)
                    
                    # Response time metric
                    if health.is_healthy and hasattr(health, 'response_time_ms'):
                        response_time_metric = AlertMetric(
                            metric_name="database_response_time_ms",
                            metric_value=health.response_time_ms,
                            database_id=db_config.id,
                            labels={"database_name": db_config.name, "role": db_config.role},
                        )
                        metrics.append(response_time_metric)
                        
                except Exception as e:
                    logger.error(f"Failed to collect metrics for database {db_config.id}: {e}")
                    
            # Collect long-running query metrics
            for db_config in db_configs:
                try:
                    health = self.connection_manager.get_health_status(db_config.id)
                    if health.is_healthy:
                        long_running_metrics = await self._collect_long_running_query_metrics(db_config.id)
                        metrics.extend(long_running_metrics)
                except Exception as e:
                    logger.error(f"Failed to collect long-running query metrics for database {db_config.id}: {e}")
                    
            # Collect replication metrics
            try:
                db_configs = await self._get_database_configs()
                if db_configs:
                    # Discover logical replication streams
                    logical_streams = await self.replication_service.discover_logical_replication(db_configs)
                    for stream in logical_streams:
                        # Collect metrics for this stream
                        try:
                            stream_metrics = await self.replication_service.collect_replication_metrics(stream)
                            if stream_metrics.lag_seconds is not None:
                                lag_metric = AlertMetric(
                                    metric_name="replication_lag_seconds",
                                    metric_value=float(stream_metrics.lag_seconds),
                                    stream_id=stream.id,
                                    database_id=stream.source_database_id,
                                    labels={
                                        "stream_type": "logical",
                                        "source_db": stream.source_database_id,
                                        "target_db": stream.target_database_id,
                                        "publication_name": stream.publication_name or "",
                                        "subscription_name": stream.subscription_name or "",
                                    },
                                )
                                metrics.append(lag_metric)
                        except Exception as e:
                            logger.debug(f"Failed to collect metrics for logical stream {stream.id}: {e}")
                        
                    # Discover physical replication streams
                    physical_streams = await self.replication_service.discover_physical_replication(db_configs)
                    for stream in physical_streams:
                        # Collect metrics for this stream
                        try:
                            stream_metrics = await self.replication_service.collect_replication_metrics(stream)
                            if stream_metrics.lag_seconds is not None:
                                lag_metric = AlertMetric(
                                    metric_name="replication_lag_seconds",
                                    metric_value=float(stream_metrics.lag_seconds),
                                    stream_id=stream.id,
                                    database_id=stream.source_database_id,
                                    labels={
                                        "stream_type": "physical",
                                        "source_db": stream.source_database_id,
                                        "target_db": stream.target_database_id,
                                    },
                                )
                                metrics.append(lag_metric)
                        except Exception as e:
                            logger.debug(f"Failed to collect metrics for physical stream {stream.id}: {e}")
                        
            except Exception as e:
                logger.error(f"Failed to collect replication metrics: {e}")
                
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            
        return metrics

    async def evaluate_thresholds(self, metrics: list[AlertMetric]) -> list[Alert]:
        """Evaluate metrics against thresholds and generate alerts"""
        alerts = []
        
        try:
            thresholds = await self.get_alert_thresholds()
            
            for threshold in thresholds:
                if not threshold.enabled:
                    continue
                    
                # Find matching metrics
                matching_metrics = [
                    m for m in metrics
                    if m.metric_name == threshold.metric_name
                    and (not threshold.target_database_id or m.database_id == threshold.target_database_id)
                    and (not threshold.target_stream_id or m.stream_id == threshold.target_stream_id)
                ]
                
                for metric in matching_metrics:
                    if self._evaluate_threshold(metric.metric_value, threshold):
                        # Check if alert already exists and is active
                        existing_alert = await self._find_existing_alert(threshold, metric)
                        
                        if not existing_alert:
                            alert = await self._create_alert(threshold, metric)
                            alerts.append(alert)
                            logger.warning(f"Generated alert: {alert.title}")
                            
        except Exception as e:
            logger.error(f"Failed to evaluate thresholds: {e}")
            
        return alerts

    def _evaluate_threshold(self, value: float, threshold: AlertThreshold) -> bool:
        """Evaluate if a metric value breaches a threshold"""
        if threshold.comparison_operator == "gt":
            return value > threshold.threshold_value
        elif threshold.comparison_operator == "gte":
            return value >= threshold.threshold_value
        elif threshold.comparison_operator == "lt":
            return value < threshold.threshold_value
        elif threshold.comparison_operator == "lte":
            return value <= threshold.threshold_value
        elif threshold.comparison_operator == "eq":
            return value == threshold.threshold_value
        return False

    async def _find_existing_alert(
        self, threshold: AlertThreshold, metric: AlertMetric
    ) -> Alert | None:
        """Find existing active alert for the same condition"""
        try:
            alerts = await self.get_active_alerts()
            for alert in alerts:
                if (
                    alert.threshold_id == threshold.id
                    and alert.database_id == metric.database_id
                    and alert.stream_id == metric.stream_id
                    and alert.status == AlertStatus.ACTIVE
                ):
                    return alert
        except Exception as e:
            logger.error(f"Failed to find existing alert: {e}")
        return None

    async def _create_alert(self, threshold: AlertThreshold, metric: AlertMetric) -> Alert:
        """Create a new alert"""
        # Generate alert title and message
        title = f"{threshold.name}: {threshold.metric_name}"
        message = self._generate_alert_message(threshold, metric)
        
        alert = Alert(
            threshold_id=threshold.id,
            alert_type=threshold.alert_type,
            severity=threshold.severity,
            title=title,
            message=message,
            database_id=metric.database_id,
            stream_id=metric.stream_id,
            metric_name=metric.metric_name,
            metric_value=metric.metric_value,
            threshold_value=threshold.threshold_value,
            details={
                "threshold_name": threshold.name,
                "threshold_description": threshold.description,
                "metric_labels": metric.labels,
                "evaluation_time": metric.timestamp.isoformat(),
            },
        )
        
        await alert.save_to_redis(self.redis_client)
        
        # Send notifications
        await self._send_alert_notifications(alert)
        
        return alert

    def _generate_alert_message(self, threshold: AlertThreshold, metric: AlertMetric) -> str:
        """Generate human-readable alert message"""
        operator_text = {
            "gt": "greater than",
            "gte": "greater than or equal to",
            "lt": "less than",
            "lte": "less than or equal to",
            "eq": "equal to",
        }
        
        op_text = operator_text.get(threshold.comparison_operator, "compared to")
        
        message = (
            f"Metric '{threshold.metric_name}' value {metric.metric_value} is "
            f"{op_text} threshold {threshold.threshold_value}"
        )
        
        if metric.database_id:
            message += f" for database {metric.database_id}"
        if metric.stream_id:
            message += f" for replication stream {metric.stream_id}"
            
        return message

    async def _send_alert_notifications(self, alert: Alert) -> None:
        """Send alert notifications through configured channels"""
        try:
            channels = await self.get_notification_channels()
            
            for channel in channels:
                if not channel.enabled:
                    continue
                    
                # Check severity filter
                if alert.severity not in channel.severity_filter:
                    continue
                    
                # Check alert type filter
                if alert.alert_type not in channel.alert_type_filter:
                    continue
                    
                await self._send_notification(channel, alert)
                
        except Exception as e:
            logger.error(f"Failed to send alert notifications: {e}")

    async def _send_notification(self, channel: NotificationChannel, alert: Alert) -> None:
        """Send notification through a specific channel"""
        try:
            if channel.channel_type == "log":
                logger.warning(
                    f"ALERT [{alert.severity.upper()}] {alert.title}: {alert.message}",
                    extra={
                        "alert_id": alert.id,
                        "alert_type": alert.alert_type,
                        "severity": alert.severity,
                        "database_id": alert.database_id,
                        "stream_id": alert.stream_id,
                    },
                )
            elif channel.channel_type == "webhook":
                # Placeholder for webhook notification
                logger.info(f"Would send webhook notification for alert {alert.id}")
            elif channel.channel_type == "email":
                # Placeholder for email notification
                logger.info(f"Would send email notification for alert {alert.id}")
            elif channel.channel_type == "slack":
                # Placeholder for Slack notification
                logger.info(f"Would send Slack notification for alert {alert.id}")
                
        except Exception as e:
            logger.error(f"Failed to send notification via {channel.channel_type}: {e}")

    async def get_system_health(self) -> SystemHealth:
        """Get overall system health status"""
        try:
            # Get active alerts
            active_alerts = await self.get_active_alerts()
            critical_alerts = [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
            warning_alerts = [a for a in active_alerts if a.severity == AlertSeverity.WARNING]
            
            # Get database health
            db_configs = await self._get_database_configs()
            healthy_dbs = 0
            for db_config in db_configs:
                health = self.connection_manager.get_health_status(db_config.id)
                if health.is_healthy:
                    healthy_dbs += 1
                    
            # Get replication health (simplified)
            healthy_streams = 0
            total_streams = 0
            try:
                if db_configs:
                    logical_streams = await self.replication_service.discover_logical_replication(db_configs)
                    physical_streams = await self.replication_service.discover_physical_replication(db_configs)
                    
                    total_streams = len(logical_streams) + len(physical_streams)
                    healthy_streams = len([
                        s for s in logical_streams + physical_streams
                        if s.status == "active"
                    ])
            except Exception as e:
                logger.debug(f"Failed to get replication health: {e}")
                
            # Determine overall status
            if critical_alerts:
                status = "critical"
            elif warning_alerts or healthy_dbs < len(db_configs):
                status = "degraded"
            else:
                status = "healthy"
                
            return SystemHealth(
                status=status,
                active_alerts=len(active_alerts),
                critical_alerts=len(critical_alerts),
                warning_alerts=len(warning_alerts),
                total_databases=len(db_configs),
                healthy_databases=healthy_dbs,
                total_streams=total_streams,
                healthy_streams=healthy_streams,
                uptime_seconds=time.time() - self.start_time,
            )
            
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return SystemHealth(
                status="critical",
                active_alerts=0,
                critical_alerts=0,
                warning_alerts=0,
                total_databases=0,
                healthy_databases=0,
                total_streams=0,
                healthy_streams=0,
                uptime_seconds=time.time() - self.start_time,
            )

    # CRUD operations for alert management
    
    async def get_alert_thresholds(self) -> list[AlertThreshold]:
        """Get all alert thresholds"""
        return await AlertThreshold.get_all_from_redis(self.redis_client)

    async def create_alert_threshold(self, threshold: AlertThreshold) -> AlertThreshold:
        """Create a new alert threshold"""
        threshold.updated_at = datetime.utcnow()
        await threshold.save_to_redis(self.redis_client)
        return threshold

    async def update_alert_threshold(self, threshold_id: str, updates: dict[str, Any]) -> AlertThreshold | None:
        """Update an alert threshold"""
        threshold = await AlertThreshold.get_from_redis(self.redis_client, threshold_id)
        if not threshold:
            return None
            
        for key, value in updates.items():
            if hasattr(threshold, key):
                setattr(threshold, key, value)
                
        threshold.updated_at = datetime.utcnow()
        await threshold.save_to_redis(self.redis_client)
        return threshold

    async def delete_alert_threshold(self, threshold_id: str) -> bool:
        """Delete an alert threshold"""
        return await AlertThreshold.delete_from_redis(self.redis_client, threshold_id)

    async def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts"""
        all_alerts = await Alert.get_all_from_redis(self.redis_client)
        return [alert for alert in all_alerts if alert.status == AlertStatus.ACTIVE]

    async def get_all_alerts(self, limit: int = 100) -> list[Alert]:
        """Get all alerts with optional limit"""
        alerts = await Alert.get_all_from_redis(self.redis_client)
        # Sort by triggered_at descending
        alerts.sort(key=lambda a: a.triggered_at, reverse=True)
        return alerts[:limit]

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> Alert | None:
        """Acknowledge an alert"""
        alert = await Alert.get_from_redis(self.redis_client, alert_id)
        if not alert:
            return None
            
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = user_id
        
        await alert.save_to_redis(self.redis_client)
        return alert

    async def resolve_alert(self, alert_id: str, user_id: str, notes: str | None = None) -> Alert | None:
        """Resolve an alert"""
        alert = await Alert.get_from_redis(self.redis_client, alert_id)
        if not alert:
            return None
            
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = user_id
        if notes:
            alert.resolution_notes = notes
            
        await alert.save_to_redis(self.redis_client)
        return alert

    async def get_notification_channels(self) -> list[NotificationChannel]:
        """Get all notification channels"""
        channels = await NotificationChannel.get_all_from_redis(self.redis_client)
        
        # Create default log channel if none exist
        if not channels:
            default_channel = NotificationChannel(
                name="Default Log Channel",
                channel_type="log",
                config={},
                enabled=True,
            )
            await default_channel.save_to_redis(self.redis_client)
            channels = [default_channel]
            
        return channels

    async def _get_database_configs(self) -> list[DatabaseConfig]:
        """Get all database configurations"""
        try:
            return await DatabaseConfig.get_all_from_redis(self.redis_client)
        except Exception as e:
            logger.error(f"Failed to get database configs: {e}")
            return []

    async def run_monitoring_cycle(self) -> None:
        """Run a single monitoring cycle"""
        try:
            logger.debug("Starting monitoring cycle")
            
            # Collect metrics
            metrics = await self.collect_metrics()
            logger.debug(f"Collected {len(metrics)} metrics")
            
            # Evaluate thresholds and generate alerts
            new_alerts = await self.evaluate_thresholds(metrics)
            if new_alerts:
                logger.info(f"Generated {len(new_alerts)} new alerts")
                
        except Exception as e:
            logger.error(f"Monitoring cycle failed: {e}")

    async def _collect_long_running_query_metrics(self, db_id: str) -> list[AlertMetric]:
        """Collect metrics for long-running queries that may impact replication"""
        metrics = []
        
        # Query to find long-running queries (>30 seconds)
        query = """
        SELECT 
            pid,
            usename,
            application_name,
            client_addr,
            state,
            query_start,
            EXTRACT(EPOCH FROM (NOW() - query_start)) as duration_seconds,
            LEFT(query, 100) as query_preview,
            backend_xmin,
            backend_xid
        FROM pg_stat_activity 
        WHERE state IN ('active', 'idle in transaction', 'idle in transaction (aborted)')
          AND query_start IS NOT NULL
          AND EXTRACT(EPOCH FROM (NOW() - query_start)) > 30
          AND pid != pg_backend_pid()  -- Exclude our own connection
          AND usename IS NOT NULL      -- Exclude background processes
        ORDER BY duration_seconds DESC
        """
        
        try:
            results = await self.connection_manager.execute_query(db_id, query)
            
            if results:
                # Count of long-running queries
                count_metric = AlertMetric(
                    metric_name="long_running_query_count",
                    metric_value=float(len(results)),
                    database_id=db_id,
                    labels={"threshold_seconds": "30"},
                )
                metrics.append(count_metric)
                
                # Maximum duration of long-running queries
                max_duration = max(row["duration_seconds"] for row in results)
                max_duration_metric = AlertMetric(
                    metric_name="long_running_query_max_duration",
                    metric_value=float(max_duration),
                    database_id=db_id,
                    labels={
                        "threshold_seconds": "30",
                        "query_count": str(len(results)),
                        "max_duration_formatted": f"{int(max_duration // 60)}m {int(max_duration % 60)}s"
                    },
                )
                metrics.append(max_duration_metric)
                
                # Log details about long-running queries for debugging
                for row in results:
                    duration_formatted = f"{int(row['duration_seconds'] // 60)}m {int(row['duration_seconds'] % 60)}s"
                    logger.warning(
                        f"Long-running query detected on {db_id}: "
                        f"PID {row['pid']}, Duration: {duration_formatted}, "
                        f"User: {row['usename']}, App: {row['application_name']}, "
                        f"Query: {row['query_preview']}..."
                    )
            else:
                # No long-running queries found
                count_metric = AlertMetric(
                    metric_name="long_running_query_count",
                    metric_value=0.0,
                    database_id=db_id,
                    labels={"threshold_seconds": "30"},
                )
                metrics.append(count_metric)
                
        except Exception as e:
            logger.error(f"Failed to collect long-running query metrics for {db_id}: {e}")
            # Return empty metrics on error to avoid breaking the monitoring cycle
            
        return metrics

    async def start_monitoring(self, interval_seconds: int = 60) -> None:
        """Start continuous monitoring (for background task)"""
        logger.info(f"Starting continuous monitoring with {interval_seconds}s interval")
        
        # Initialize default thresholds
        await self.initialize_default_thresholds()
        
        while True:
            try:
                await self.run_monitoring_cycle()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info("Monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(interval_seconds)