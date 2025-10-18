"""
Integration tests for the alerting system
"""

from app.models.alerts import AlertSeverity, AlertThreshold, AlertType


class TestAlertingModels:
    """Test alerting models"""

    def test_alert_threshold_model(self):
        """Test AlertThreshold model validation"""
        threshold = AlertThreshold(
            alert_type=AlertType.REPLICATION_LAG,
            severity=AlertSeverity.WARNING,
            metric_name="replication_lag_seconds",
            threshold_value=300.0,
            name="Test Threshold",
            description="Test threshold for validation",
        )

        assert threshold.alert_type == AlertType.REPLICATION_LAG
        assert threshold.severity == AlertSeverity.WARNING
        assert threshold.metric_name == "replication_lag_seconds"
        assert threshold.threshold_value == 300.0
        assert threshold.comparison_operator == "gt"  # Default value
        assert threshold.enabled is True  # Default value

    def test_alert_threshold_validation(self):
        """Test AlertThreshold validation"""
        # Test that threshold can be created with valid values
        threshold = AlertThreshold(
            alert_type=AlertType.REPLICATION_LAG,
            severity=AlertSeverity.WARNING,
            metric_name="test_metric",
            threshold_value=100.0,
            name="Valid Threshold",
        )
        assert threshold.threshold_value == 100.0

        # Test that negative values are allowed (for some metrics like response time differences)
        AlertThreshold(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.WARNING,
            metric_name="test_metric",
            threshold_value=-1.0,
            name="Negative Threshold",
        )

    def test_long_running_query_alert_type(self):
        """Test long-running query alert type"""
        threshold = AlertThreshold(
            alert_type=AlertType.LONG_RUNNING_QUERY,
            severity=AlertSeverity.WARNING,
            metric_name="long_running_query_count",
            threshold_value=1.0,
            comparison_operator="gte",
            name="Long Running Query Alert",
            description="Alert when queries run longer than 30 seconds",
        )

        assert threshold.alert_type == AlertType.LONG_RUNNING_QUERY
        assert threshold.metric_name == "long_running_query_count"
        assert threshold.comparison_operator == "gte"
        assert threshold.threshold_value == 1.0

    def test_alert_model_creation(self):
        """Test Alert model creation"""
        from app.models.alerts import Alert

        alert = Alert(
            threshold_id="test-threshold-id",
            alert_type=AlertType.DATABASE_CONNECTION,
            severity=AlertSeverity.CRITICAL,
            title="Test Alert",
            message="This is a test alert",
            metric_name="database_connection_failed",
            metric_value=1.0,
            threshold_value=1.0,
        )

        assert alert.alert_type == AlertType.DATABASE_CONNECTION
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.title == "Test Alert"
        assert alert.metric_value == 1.0

    def test_system_health_model(self):
        """Test SystemHealth model"""
        from app.models.alerts import SystemHealth

        health = SystemHealth(
            status="healthy",
            total_databases=3,
            healthy_databases=3,
            total_streams=2,
            healthy_streams=2,
        )

        assert health.status == "healthy"
        assert health.total_databases == 3
        assert health.healthy_databases == 3
        assert health.active_alerts == 0  # Default value

    def test_notification_channel_model(self):
        """Test NotificationChannel model"""
        from app.models.alerts import NotificationChannel

        channel = NotificationChannel(
            name="Test Log Channel",
            channel_type="log",
            config={},
        )

        assert channel.name == "Test Log Channel"
        assert channel.channel_type == "log"
        assert channel.enabled is True  # Default value
        assert AlertSeverity.CRITICAL in channel.severity_filter  # Default includes all


class TestAlertingAPI:
    """Test alerting API endpoints"""

    def test_alerting_api_endpoints_exist(self, client):
        """Test that alerting API endpoints exist"""
        # These should return 401 (auth required) or 503 (service unavailable) not 404 (not found)

        # Test health endpoint
        response = client.get("/api/alerts/health")
        assert response.status_code in [401, 503]  # Auth required or service unavailable, but endpoint exists

        # Test thresholds endpoint
        response = client.get("/api/alerts/thresholds")
        assert response.status_code in [401, 503]  # Auth required or service unavailable, but endpoint exists

        # Test metrics summary endpoint
        response = client.get("/api/alerts/metrics/summary")
        assert response.status_code in [401, 503]  # Auth required or service unavailable, but endpoint exists

        # Test monitoring trigger endpoint
        response = client.post("/api/alerts/test-monitoring")
        assert response.status_code == 401  # Auth required, but endpoint exists

    def test_alert_models_serialization(self):
        """Test that alert models can be serialized"""
        threshold = AlertThreshold(
            alert_type=AlertType.REPLICATION_LAG,
            severity=AlertSeverity.WARNING,
            metric_name="replication_lag_seconds",
            threshold_value=300.0,
            name="Test Threshold",
        )

        # Test JSON serialization
        json_data = threshold.model_dump_json()
        assert isinstance(json_data, str)
        assert "replication_lag" in json_data
        assert "300.0" in json_data

        # Test deserialization
        restored_threshold = AlertThreshold.model_validate_json(json_data)
        assert restored_threshold.alert_type == threshold.alert_type
        assert restored_threshold.threshold_value == threshold.threshold_value

    def test_alert_enum_values(self):
        """Test alert enum values"""
        # Test AlertType enum
        assert AlertType.REPLICATION_LAG == "replication_lag"
        assert AlertType.DATABASE_CONNECTION == "database_connection"
        assert AlertType.SYSTEM_ERROR == "system_error"

        # Test AlertSeverity enum
        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.INFO == "info"

        # Test AlertStatus enum
        from app.models.alerts import AlertStatus

        assert AlertStatus.ACTIVE == "active"
        assert AlertStatus.ACKNOWLEDGED == "acknowledged"
        assert AlertStatus.RESOLVED == "resolved"
