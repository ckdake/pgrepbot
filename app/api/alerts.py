"""
Alerts and monitoring API endpoints
"""

import logging
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_redis_client
from app.middleware.auth import get_current_user, require_admin, require_viewer
from app.models.alerts import (
    Alert,
    AlertThreshold,
    NotificationChannel,
    SystemHealth,
)
from app.models.auth import User
from app.services.alerting import AlertingService
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


async def get_alerting_service(
    redis_client: redis.Redis = Depends(get_redis_client),
) -> AlertingService:
    """Get alerting service instance"""
    from app.services.aws_rds import RDSClient
    from app.services.aws_secrets import SecretsManagerClient

    # Create AWS clients for credential resolution
    secrets_client = SecretsManagerClient()
    rds_client = RDSClient()

    connection_manager = PostgreSQLConnectionManager(secrets_client=secrets_client, rds_client=rds_client)

    # Don't add databases here to avoid connection pool conflicts
    # The alerting service will get database health from the database test API

    replication_service = ReplicationDiscoveryService(connection_manager, redis_client)
    return AlertingService(redis_client, connection_manager, replication_service)


@router.get("/health", response_model=SystemHealth)
async def get_system_health(
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_viewer),
):
    """Get overall system health status"""
    try:
        return await alerting_service.get_system_health()
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system health: {str(e)}",
        ) from e


@router.get("/active", response_model=list[Alert])
async def get_active_alerts(
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_viewer),
):
    """Get all active alerts"""
    try:
        return await alerting_service.get_active_alerts()
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active alerts: {str(e)}",
        ) from e


@router.get("/", response_model=list[Alert])
async def get_all_alerts(
    limit: int = 100,
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_viewer),
):
    """Get all alerts with optional limit"""
    try:
        return await alerting_service.get_all_alerts(limit=limit)
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get alerts: {str(e)}",
        ) from e


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    alerting_service: AlertingService = Depends(get_alerting_service),
    user: User = Depends(get_current_user),
):
    """Acknowledge an alert"""
    try:
        alert = await alerting_service.acknowledge_alert(alert_id, user.id)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found",
            )
        return {"success": True, "message": "Alert acknowledged", "alert": alert}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to acknowledge alert: {str(e)}",
        ) from e


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_data: dict[str, Any],
    alerting_service: AlertingService = Depends(get_alerting_service),
    user: User = Depends(get_current_user),
):
    """Resolve an alert"""
    try:
        notes = resolution_data.get("notes")
        alert = await alerting_service.resolve_alert(alert_id, user.id, notes)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found",
            )
        return {"success": True, "message": "Alert resolved", "alert": alert}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve alert: {str(e)}",
        ) from e


@router.get("/thresholds", response_model=list[AlertThreshold])
async def get_alert_thresholds(
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_viewer),
):
    """Get all alert thresholds"""
    try:
        return await alerting_service.get_alert_thresholds()
    except Exception as e:
        logger.error(f"Failed to get alert thresholds: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get alert thresholds: {str(e)}",
        ) from e


@router.post("/thresholds", response_model=AlertThreshold)
async def create_alert_threshold(
    threshold: AlertThreshold,
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_admin),
):
    """Create a new alert threshold"""
    try:
        return await alerting_service.create_alert_threshold(threshold)
    except Exception as e:
        logger.error(f"Failed to create alert threshold: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create alert threshold: {str(e)}",
        ) from e


@router.put("/thresholds/{threshold_id}", response_model=AlertThreshold)
async def update_alert_threshold(
    threshold_id: str,
    updates: dict[str, Any],
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_admin),
):
    """Update an alert threshold"""
    try:
        threshold = await alerting_service.update_alert_threshold(threshold_id, updates)
        if not threshold:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert threshold {threshold_id} not found",
            )
        return threshold
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update alert threshold {threshold_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update alert threshold: {str(e)}",
        ) from e


@router.delete("/thresholds/{threshold_id}")
async def delete_alert_threshold(
    threshold_id: str,
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_admin),
):
    """Delete an alert threshold"""
    try:
        success = await alerting_service.delete_alert_threshold(threshold_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert threshold {threshold_id} not found",
            )
        return {"success": True, "message": "Alert threshold deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete alert threshold {threshold_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete alert threshold: {str(e)}",
        ) from e


@router.get("/channels", response_model=list[NotificationChannel])
async def get_notification_channels(
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_viewer),
):
    """Get all notification channels"""
    try:
        return await alerting_service.get_notification_channels()
    except Exception as e:
        logger.error(f"Failed to get notification channels: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notification channels: {str(e)}",
        ) from e


@router.post("/test-monitoring")
async def test_monitoring_cycle(
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_admin),
):
    """Manually trigger a monitoring cycle for testing"""
    try:
        await alerting_service.run_monitoring_cycle()
        return {"success": True, "message": "Monitoring cycle completed"}
    except Exception as e:
        logger.error(f"Failed to run monitoring cycle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run monitoring cycle: {str(e)}",
        ) from e


@router.get("/metrics/summary")
async def get_metrics_summary(
    alerting_service: AlertingService = Depends(get_alerting_service),
    _user: User = Depends(require_viewer),
):
    """Get summary of current metrics"""
    try:
        metrics = await alerting_service.collect_metrics()

        # Group metrics by type
        summary = {}
        for metric in metrics:
            metric_type = metric.metric_name
            if metric_type not in summary:
                summary[metric_type] = {
                    "count": 0,
                    "values": [],
                    "avg": 0.0,
                    "min": float("inf"),
                    "max": float("-inf"),
                }

            summary[metric_type]["count"] += 1
            summary[metric_type]["values"].append(metric.metric_value)
            summary[metric_type]["min"] = min(summary[metric_type]["min"], metric.metric_value)
            summary[metric_type]["max"] = max(summary[metric_type]["max"], metric.metric_value)

        # Calculate averages
        for metric_type in summary:
            values = summary[metric_type]["values"]
            summary[metric_type]["avg"] = sum(values) / len(values) if values else 0.0
            # Remove raw values from response
            del summary[metric_type]["values"]

        return {
            "total_metrics": len(metrics),
            "metric_types": len(summary),
            "metrics_by_type": summary,
            "collection_time": metrics[0].timestamp.isoformat() if metrics else None,
        }
    except Exception as e:
        logger.error(f"Failed to get metrics summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics summary: {str(e)}",
        ) from e
