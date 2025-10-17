"""
Alert and monitoring models
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.migration import DatetimeSerializer
from app.utils.redis_serializer import RedisModelMixin


class AlertSeverity(str, Enum):
    """Alert severity levels"""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, Enum):
    """Alert status"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertType(str, Enum):
    """Types of alerts"""

    REPLICATION_LAG = "replication_lag"
    REPLICATION_FAILURE = "replication_failure"
    DATABASE_CONNECTION = "database_connection"
    MIGRATION_FAILURE = "migration_failure"
    SYSTEM_ERROR = "system_error"


class AlertThreshold(BaseModel, RedisModelMixin):
    """Alert threshold configuration"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    alert_type: AlertType = Field(..., description="Type of alert")
    severity: AlertSeverity = Field(..., description="Alert severity")
    
    # Threshold configuration
    metric_name: str = Field(..., description="Metric to monitor")
    threshold_value: float = Field(..., description="Threshold value")
    comparison_operator: Literal["gt", "lt", "eq", "gte", "lte"] = Field(
        default="gt", description="Comparison operator"
    )
    
    # Timing configuration
    evaluation_window_seconds: int = Field(
        default=300, description="Time window for evaluation in seconds"
    )
    consecutive_breaches: int = Field(
        default=2, description="Number of consecutive breaches before alerting"
    )
    
    # Targeting
    target_database_id: str | None = Field(None, description="Specific database to monitor")
    target_stream_id: str | None = Field(None, description="Specific replication stream to monitor")
    
    # Metadata
    name: str = Field(..., description="Human-readable threshold name")
    description: str | None = Field(None, description="Threshold description")
    enabled: bool = Field(default=True, description="Whether threshold is enabled")
    
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    updated_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)


class Alert(BaseModel, RedisModelMixin):
    """Alert instance"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    threshold_id: str = Field(..., description="ID of the threshold that triggered this alert")
    
    # Alert details
    alert_type: AlertType = Field(..., description="Type of alert")
    severity: AlertSeverity = Field(..., description="Alert severity")
    status: AlertStatus = Field(default=AlertStatus.ACTIVE, description="Alert status")
    
    # Alert content
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional alert details")
    
    # Context
    database_id: str | None = Field(None, description="Related database ID")
    stream_id: str | None = Field(None, description="Related replication stream ID")
    migration_id: str | None = Field(None, description="Related migration ID")
    
    # Metrics
    metric_name: str | None = Field(None, description="Metric that triggered the alert")
    metric_value: float | None = Field(None, description="Current metric value")
    threshold_value: float | None = Field(None, description="Threshold value that was breached")
    
    # Timing
    triggered_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    acknowledged_at: DatetimeSerializer | None = Field(None, description="When alert was acknowledged")
    resolved_at: DatetimeSerializer | None = Field(None, description="When alert was resolved")
    
    # User actions
    acknowledged_by: str | None = Field(None, description="User who acknowledged the alert")
    resolved_by: str | None = Field(None, description="User who resolved the alert")
    resolution_notes: str | None = Field(None, description="Notes about alert resolution")


class AlertRule(BaseModel, RedisModelMixin):
    """Alert rule configuration"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Rule name")
    description: str | None = Field(None, description="Rule description")
    
    # Rule conditions
    alert_type: AlertType = Field(..., description="Type of alert this rule handles")
    conditions: dict[str, Any] = Field(..., description="Rule conditions")
    
    # Actions
    notification_channels: list[str] = Field(
        default_factory=list, description="Notification channels to use"
    )
    auto_resolve: bool = Field(default=False, description="Whether to auto-resolve when conditions clear")
    
    # Configuration
    enabled: bool = Field(default=True, description="Whether rule is enabled")
    priority: int = Field(default=100, description="Rule priority (lower = higher priority)")
    
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    updated_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)


class NotificationChannel(BaseModel, RedisModelMixin):
    """Notification channel configuration"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Channel name")
    channel_type: Literal["email", "webhook", "slack", "log"] = Field(..., description="Channel type")
    
    # Configuration
    config: dict[str, Any] = Field(..., description="Channel-specific configuration")
    enabled: bool = Field(default=True, description="Whether channel is enabled")
    
    # Filtering
    severity_filter: list[AlertSeverity] = Field(
        default_factory=lambda: list(AlertSeverity), description="Severities to include"
    )
    alert_type_filter: list[AlertType] = Field(
        default_factory=lambda: list(AlertType), description="Alert types to include"
    )
    
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    updated_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)


class SystemHealth(BaseModel):
    """System health status"""

    model_config = ConfigDict(str_strip_whitespace=True)

    # Overall status
    status: Literal["healthy", "degraded", "critical"] = Field(..., description="Overall system status")
    
    # Component health
    database_health: dict[str, Any] = Field(default_factory=dict, description="Database health status")
    replication_health: dict[str, Any] = Field(default_factory=dict, description="Replication health status")
    aws_health: dict[str, Any] = Field(default_factory=dict, description="AWS services health status")
    
    # Active alerts
    active_alerts: int = Field(default=0, description="Number of active alerts")
    critical_alerts: int = Field(default=0, description="Number of critical alerts")
    warning_alerts: int = Field(default=0, description="Number of warning alerts")
    
    # Metrics
    total_databases: int = Field(default=0, description="Total number of databases")
    healthy_databases: int = Field(default=0, description="Number of healthy databases")
    total_streams: int = Field(default=0, description="Total number of replication streams")
    healthy_streams: int = Field(default=0, description="Number of healthy replication streams")
    
    # Timing
    last_check: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    uptime_seconds: float = Field(default=0.0, description="System uptime in seconds")


class AlertMetric(BaseModel):
    """Alert metric data point"""

    model_config = ConfigDict(str_strip_whitespace=True)

    metric_name: str = Field(..., description="Metric name")
    metric_value: float = Field(..., description="Metric value")
    timestamp: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    
    # Context
    database_id: str | None = Field(None, description="Related database ID")
    stream_id: str | None = Field(None, description="Related stream ID")
    labels: dict[str, str] = Field(default_factory=dict, description="Additional metric labels")