"""
Tests for the alerting service
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis

from app.models.alerts import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertThreshold,
    AlertType,
)
from app.models.database import DatabaseConfig
from app.models.replication import ReplicationMetrics, ReplicationStream
from app.services.alerting import AlertingService
from app.services.postgres_connection import ConnectionHealth, PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService


class TestAlertingService:
    """Test the AlertingService class"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        return AsyncMock(spec=redis.Redis)

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock PostgreSQL connection manager"""
        return MagicMock(spec=PostgreSQLConnectionManager)

    @pytest.fixture
    def mock_replication_service(self):
        """Mock replication discovery service"""
        return AsyncMock(spec=ReplicationDiscoveryService)

    @pytest.fixture
    def alerting_service(self, mock_redis, mock_connection_manager, mock_replication_service):
        """Create AlertingService instance with mocked dependencies"""
        return AlertingService(
            redis_client=mock_redis,
            connection_manager=mock_connection_manager,
            replication_service=mock_replication_service,
        )

    def test_init(self, alerting_service, mock_redis, mock_connection_manager, mock_replication_service):
        """Test AlertingService initialization"""
        assert alerting_service.redis_client == mock_redis
        assert alerting_service.connection_manager == mock_connection_manager
        assert alerting_service.replication_service == mock_replication_service
        assert isinstance(alerting_service.start_time, float)
        assert len(alerting_service._default_thresholds) == 5

    def test_default_thresholds(self, alerting_service):
        """Test default alert thresholds are properly configured"""
        thresholds = alerting_service._default_thresholds

        # Check we have the expected threshold types
        threshold_types = [t.alert_type for t in thresholds]
        assert AlertType.REPLICATION_LAG in threshold_types
        assert AlertType.DATABASE_CONNECTION in threshold_types
        assert AlertType.LONG_RUNNING_QUERY in threshold_types

        # Check replication lag thresholds
        replication_thresholds = [t for t in thresholds if t.alert_type == AlertType.REPLICATION_LAG]
        assert len(replication_thresholds) == 2

        warning_threshold = next(t for t in replication_thresholds if t.severity == AlertSeverity.WARNING)
        assert warning_threshold.threshold_value == 300.0

        critical_threshold = next(t for t in replication_thresholds if t.severity == AlertSeverity.CRITICAL)
        assert critical_threshold.threshold_value == 1800.0

    async def test_initialize_default_thresholds_no_existing(self, alerting_service):
        """Test initializing default thresholds when none exist"""
        # Mock no existing thresholds
        alerting_service.get_alert_thresholds = AsyncMock(return_value=[])

        # Mock save_to_redis for each threshold
        with patch.object(AlertThreshold, 'save_to_redis', new_callable=AsyncMock) as mock_save:
            await alerting_service.initialize_default_thresholds()

            # Should save all default thresholds
            assert mock_save.call_count == len(alerting_service._default_thresholds)

    async def test_initialize_default_thresholds_existing(self, alerting_service):
        """Test initializing default thresholds when some exist"""
        # Mock existing thresholds
        existing_threshold = AlertThreshold(
            alert_type=AlertType.REPLICATION_LAG,
            severity=AlertSeverity.WARNING,
            metric_name="replication_lag_seconds",
            threshold_value=300.0,
            name="Existing Threshold",
            description="Existing threshold",
        )
        alerting_service.get_alert_thresholds = AsyncMock(return_value=[existing_threshold])

        # Mock save_to_redis
        with patch.object(AlertThreshold, 'save_to_redis', new_callable=AsyncMock) as mock_save:
            await alerting_service.initialize_default_thresholds()

            # Should not save any thresholds since some exist
            mock_save.assert_not_called()

    async def test_initialize_default_thresholds_error(self, alerting_service):
        """Test initializing default thresholds with error"""
        # Mock get_alert_thresholds to raise an exception
        alerting_service.get_alert_thresholds = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise exception
        await alerting_service.initialize_default_thresholds()

    async def test_collect_metrics_database_health(self, alerting_service, mock_connection_manager):
        """Test collecting database health metrics"""
        # Mock database configs
        db_config = DatabaseConfig(
            id="test-db",
            name="Test Database",
            host="localhost",
            port=5432,
            database="testdb",
            role="primary",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-credentials",
            environment="test",
            cloud_provider="aws",
        )
        alerting_service._get_database_configs = AsyncMock(return_value=[db_config])

        # Mock healthy database
        healthy_status = ConnectionHealth(
            is_healthy=True,
            last_check=datetime.now(UTC),
            response_time_ms=50.0,
        )
        mock_connection_manager.get_health_status.return_value = healthy_status

        # Mock auto-resolve method
        alerting_service._auto_resolve_database_connection_alerts = AsyncMock()

        # Mock long-running query metrics
        alerting_service._collect_long_running_query_metrics = AsyncMock(return_value=[])

        # Mock replication discovery to return empty lists
        alerting_service.replication_service.discover_logical_replication.return_value = []
        alerting_service.replication_service.discover_physical_replication.return_value = []

        metrics = await alerting_service.collect_metrics()

        # Should have database connection and response time metrics
        assert len(metrics) >= 2

        connection_metric = next(m for m in metrics if m.metric_name == "database_connection_failed")
        assert connection_metric.metric_value == 0.0  # Healthy
        assert connection_metric.database_id == "test-db"

        response_metric = next(m for m in metrics if m.metric_name == "database_response_time_ms")
        assert response_metric.metric_value == 50.0
        assert response_metric.database_id == "test-db"

        # Should auto-resolve connection alerts for healthy database
        alerting_service._auto_resolve_database_connection_alerts.assert_called_once_with("test-db")

    async def test_collect_metrics_database_unhealthy(self, alerting_service, mock_connection_manager):
        """Test collecting metrics for unhealthy database"""
        # Mock database configs
        db_config = DatabaseConfig(
            id="test-db",
            name="Test Database",
            host="localhost",
            port=5432,
            database="testdb",
            role="primary",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-credentials",
            environment="test",
            cloud_provider="aws",
        )
        alerting_service._get_database_configs = AsyncMock(return_value=[db_config])

        # Mock unhealthy database
        unhealthy_status = ConnectionHealth(
            is_healthy=False,
            last_check=datetime.now(UTC),
            error_message="Connection failed",
        )
        mock_connection_manager.get_health_status.return_value = unhealthy_status

        # Mock auto-resolve method
        alerting_service._auto_resolve_database_connection_alerts = AsyncMock()

        # Mock long-running query metrics
        alerting_service._collect_long_running_query_metrics = AsyncMock(return_value=[])

        # Mock replication discovery to return empty lists
        alerting_service.replication_service.discover_logical_replication.return_value = []
        alerting_service.replication_service.discover_physical_replication.return_value = []

        metrics = await alerting_service.collect_metrics()

        # Should have database connection metric
        connection_metric = next(m for m in metrics if m.metric_name == "database_connection_failed")
        assert connection_metric.metric_value == 1.0  # Unhealthy
        assert connection_metric.database_id == "test-db"

        # Should not auto-resolve connection alerts for unhealthy database
        alerting_service._auto_resolve_database_connection_alerts.assert_not_called()

    async def test_collect_metrics_replication_lag(self, alerting_service, mock_connection_manager):
        """Test collecting replication lag metrics"""
        # Mock database configs
        db_config = DatabaseConfig(
            id="test-db",
            name="Test Database",
            host="localhost",
            port=5432,
            database="testdb",
            role="primary",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-credentials",
            environment="test",
            cloud_provider="aws",
        )
        alerting_service._get_database_configs = AsyncMock(return_value=[db_config])

        # Mock healthy database
        healthy_status = ConnectionHealth(is_healthy=True, last_check=datetime.now(UTC))
        mock_connection_manager.get_health_status.return_value = healthy_status

        # Mock auto-resolve and long-running query methods
        alerting_service._auto_resolve_database_connection_alerts = AsyncMock()
        alerting_service._collect_long_running_query_metrics = AsyncMock(return_value=[])

        # Mock logical replication stream
        logical_stream = ReplicationStream(
            id="550e8400-e29b-41d4-a716-446655440000",
            source_db_id="550e8400-e29b-41d4-a716-446655440001",
            target_db_id="550e8400-e29b-41d4-a716-446655440002",
            type="logical",
            publication_name="test_pub",
            subscription_name="test_sub",
            status="active",
        )

        # Mock replication metrics
        replication_metrics = ReplicationMetrics(
            stream_id="logical-stream-1",
            lag_seconds=120.0,
            lag_bytes=1024,
        )

        alerting_service.replication_service.discover_logical_replication.return_value = [logical_stream]
        alerting_service.replication_service.collect_replication_metrics.return_value = replication_metrics
        alerting_service.replication_service.discover_physical_replication.return_value = []

        metrics = await alerting_service.collect_metrics()

        # Should have replication lag metric
        lag_metrics = [m for m in metrics if m.metric_name == "replication_lag_seconds"]
        assert len(lag_metrics) == 1

        lag_metric = lag_metrics[0]
        assert lag_metric.metric_value == 120.0
        assert lag_metric.stream_id == "logical-stream-1"
        assert lag_metric.database_id == "test-db"
        assert lag_metric.labels["stream_type"] == "logical"

    async def test_collect_metrics_error_handling(self, alerting_service):
        """Test error handling in collect_metrics"""
        # Mock _get_database_configs to raise an exception
        alerting_service._get_database_configs = AsyncMock(side_effect=Exception("Database config error"))

        # Should not raise exception and return empty metrics
        metrics = await alerting_service.collect_metrics()
        assert metrics == []


class TestAlertingServiceHelperMethods:
    """Test helper methods of AlertingService"""

    @pytest.fixture
    def alerting_service(self):
        """Create AlertingService instance with mocked dependencies"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_connection_manager = MagicMock(spec=PostgreSQLConnectionManager)
        mock_replication_service = AsyncMock(spec=ReplicationDiscoveryService)

        return AlertingService(
            redis_client=mock_redis,
            connection_manager=mock_connection_manager,
            replication_service=mock_replication_service,
        )

    async def test_get_database_configs(self, alerting_service):
        """Test _get_database_configs method"""
        # Mock Redis response
        mock_configs_data = [
            {
                "id": "db1",
                "name": "Database 1",
                "host": "localhost",
                "port": 5432,
                "database": "db1",
                "role": "primary",
            }
        ]

        with patch("app.models.database.DatabaseConfig.load_all_from_redis", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = [
                DatabaseConfig(
                    id="db1",
                    name="Database 1",
                    host="localhost",
                    port=5432,
                    database="db1",
                    role="primary",
                    credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:db1-credentials",
                    environment="test",
                    cloud_provider="aws",
                )
            ]

            configs = await alerting_service._get_database_configs()
            assert len(configs) == 1
            assert configs[0].id == "db1"

    async def test_auto_resolve_database_connection_alerts(self, alerting_service):
        """Test _auto_resolve_database_connection_alerts method"""
        # Mock existing alerts
        existing_alert = Alert(
            id="alert-1",
            alert_type=AlertType.DATABASE_CONNECTION,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            title="Database Connection Failed",
            description="Database connection failed",
            database_id="test-db",
            created_at=datetime.now(UTC),
        )

        with patch("app.models.alerts.Alert.load_all_from_redis") as mock_load:
            mock_load.return_value = [existing_alert]

            with patch.object(existing_alert, "save_to_redis", new_callable=AsyncMock) as mock_save:
                await alerting_service._auto_resolve_database_connection_alerts("test-db")

                # Alert should be resolved
                assert existing_alert.status == AlertStatus.RESOLVED
                mock_save.assert_called_once()


class TestAlertingServiceIntegration:
    """Integration tests for AlertingService"""

    @pytest.fixture
    async def redis_client(self):
        """Real Redis client for integration tests"""
        client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)
        yield client
        # Cleanup
        await client.flushdb()
        await client.aclose()

    @pytest.fixture
    def alerting_service_real_redis(self, redis_client):
        """AlertingService with real Redis client"""
        mock_connection_manager = MagicMock(spec=PostgreSQLConnectionManager)
        mock_replication_service = AsyncMock(spec=ReplicationDiscoveryService)

        return AlertingService(
            redis_client=redis_client,
            connection_manager=mock_connection_manager,
            replication_service=mock_replication_service,
        )

    async def test_initialize_and_get_thresholds_integration(self, alerting_service_real_redis):
        """Test initializing and retrieving thresholds with real Redis"""
        # Initialize default thresholds
        await alerting_service_real_redis.initialize_default_thresholds()

        # Get thresholds
        thresholds = await alerting_service_real_redis.get_alert_thresholds()

        # Should have default thresholds
        assert len(thresholds) == len(alerting_service_real_redis._default_thresholds)

        # Check threshold types
        threshold_types = [t.alert_type for t in thresholds]
        assert AlertType.REPLICATION_LAG in threshold_types
        assert AlertType.DATABASE_CONNECTION in threshold_types
        assert AlertType.LONG_RUNNING_QUERY in threshold_types
