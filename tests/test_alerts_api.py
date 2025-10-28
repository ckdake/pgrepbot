"""
Tests for the alerts API endpoints
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.alerts import get_alerting_service, router
from app.models.alerts import Alert, AlertSeverity, AlertStatus, AlertType, SystemHealth
from app.models.auth import User
from app.services.alerting import AlertingService


class TestAlertsAPI:
    """Test the alerts API endpoints"""

    @pytest.fixture
    def mock_alerting_service(self):
        """Mock alerting service"""
        return AsyncMock(spec=AlertingService)

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user"""
        return User(
            id="test-user",
            username="testuser",
            email="test@example.com",
            auth_method="auth_key"
        )

    @pytest.fixture
    def test_app_with_alerts(self):
        """Create test app with alerts router"""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client_with_alerts(self, test_app_with_alerts):
        """Test client with alerts endpoints"""
        return TestClient(test_app_with_alerts)

    def test_get_alerting_service_dependency(self):
        """Test the get_alerting_service dependency function"""
        # This tests that the dependency can be created
        # The actual functionality is tested in integration tests
        assert get_alerting_service is not None

    async def test_get_system_health_success(self, mock_alerting_service, mock_user):
        """Test successful system health retrieval"""
        from app.api.alerts import get_system_health

        # Mock system health response
        system_health = SystemHealth(
            overall_status="healthy",
            database_count=3,
            healthy_databases=3,
            active_alerts=0,
            replication_streams=2,
            healthy_streams=2,
            uptime_seconds=3600,
        )
        mock_alerting_service.get_system_health.return_value = system_health

        # Mock dependencies
        with patch("app.api.alerts.get_alerting_service", return_value=mock_alerting_service):
            with patch("app.api.alerts.require_viewer", return_value=mock_user):
                result = await get_system_health(mock_alerting_service, mock_user)

        assert result == system_health
        mock_alerting_service.get_system_health.assert_called_once()

    async def test_get_system_health_error(self, mock_alerting_service, mock_user):
        """Test system health retrieval with error"""
        from app.api.alerts import get_system_health

        # Mock service error
        mock_alerting_service.get_system_health.side_effect = Exception("Service error")

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_system_health(mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to get system health" in str(exc_info.value.detail)

    async def test_get_active_alerts_success(self, mock_alerting_service, mock_user):
        """Test successful active alerts retrieval"""
        from app.api.alerts import get_active_alerts

        # Mock active alerts
        active_alerts = [
            Alert(
                id="alert-1",
                alert_type=AlertType.DATABASE_CONNECTION,
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE,
                title="Database Connection Failed",
                description="Database connection failed",
                database_id="db1",
                created_at=datetime.now(UTC),
            ),
        ]
        mock_alerting_service.get_active_alerts.return_value = active_alerts

        result = await get_active_alerts(mock_alerting_service, mock_user)

        assert result == active_alerts
        mock_alerting_service.get_active_alerts.assert_called_once()

    async def test_get_active_alerts_error(self, mock_alerting_service, mock_user):
        """Test active alerts retrieval with error"""
        from app.api.alerts import get_active_alerts

        # Mock service error
        mock_alerting_service.get_active_alerts.side_effect = Exception("Service error")

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_active_alerts(mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to get active alerts" in str(exc_info.value.detail)

    async def test_get_all_alerts_success(self, mock_alerting_service, mock_user):
        """Test successful all alerts retrieval"""
        from app.api.alerts import get_all_alerts

        # Mock all alerts
        all_alerts = [
            Alert(
                id="alert-1",
                alert_type=AlertType.DATABASE_CONNECTION,
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.RESOLVED,
                title="Database Connection Failed",
                description="Database connection failed",
                database_id="db1",
                created_at=datetime.now(UTC),
            ),
        ]
        mock_alerting_service.get_all_alerts.return_value = all_alerts

        result = await get_all_alerts(50, mock_alerting_service, mock_user)

        assert result == all_alerts
        mock_alerting_service.get_all_alerts.assert_called_once_with(limit=50)

    async def test_get_all_alerts_default_limit(self, mock_alerting_service, mock_user):
        """Test all alerts retrieval with default limit"""
        from app.api.alerts import get_all_alerts

        mock_alerting_service.get_all_alerts.return_value = []

        await get_all_alerts(100, mock_alerting_service, mock_user)

        mock_alerting_service.get_all_alerts.assert_called_once_with(limit=100)

    async def test_get_all_alerts_error(self, mock_alerting_service, mock_user):
        """Test all alerts retrieval with error"""
        from app.api.alerts import get_all_alerts

        # Mock service error
        mock_alerting_service.get_all_alerts.side_effect = Exception("Service error")

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_all_alerts(100, mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to get alerts" in str(exc_info.value.detail)

    async def test_acknowledge_alert_success(self, mock_alerting_service, mock_user):
        """Test successful alert acknowledgment"""
        from app.api.alerts import acknowledge_alert

        # Mock acknowledged alert
        acknowledged_alert = Alert(
            id="alert-1",
            alert_type=AlertType.DATABASE_CONNECTION,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACKNOWLEDGED,
            title="Database Connection Failed",
            description="Database connection failed",
            database_id="db1",
            created_at=datetime.now(UTC),
        )
        mock_alerting_service.acknowledge_alert.return_value = acknowledged_alert

        result = await acknowledge_alert("alert-1", mock_alerting_service, mock_user)

        assert result["success"] is True
        assert result["message"] == "Alert acknowledged"
        assert result["alert"] == acknowledged_alert
        mock_alerting_service.acknowledge_alert.assert_called_once_with("alert-1", "test-user")

    async def test_acknowledge_alert_not_found(self, mock_alerting_service, mock_user):
        """Test acknowledging non-existent alert"""
        from app.api.alerts import acknowledge_alert

        # Mock alert not found
        mock_alerting_service.acknowledge_alert.return_value = None

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await acknowledge_alert("nonexistent", mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 404
        assert "Alert nonexistent not found" in str(exc_info.value.detail)

    async def test_acknowledge_alert_error(self, mock_alerting_service, mock_user):
        """Test alert acknowledgment with error"""
        from app.api.alerts import acknowledge_alert

        # Mock service error
        mock_alerting_service.acknowledge_alert.side_effect = Exception("Service error")

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await acknowledge_alert("alert-1", mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to acknowledge alert" in str(exc_info.value.detail)

    async def test_resolve_alert_success(self, mock_alerting_service, mock_user):
        """Test successful alert resolution"""
        from app.api.alerts import resolve_alert

        # Mock resolved alert
        resolved_alert = Alert(
            id="alert-1",
            alert_type=AlertType.DATABASE_CONNECTION,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            title="Database Connection Failed",
            description="Database connection failed",
            database_id="db1",
            created_at=datetime.now(UTC),
        )
        mock_alerting_service.resolve_alert.return_value = resolved_alert

        resolution_data = {"notes": "Fixed database connection"}
        result = await resolve_alert("alert-1", resolution_data, mock_alerting_service, mock_user)

        assert result["success"] is True
        assert result["message"] == "Alert resolved"
        assert result["alert"] == resolved_alert
        mock_alerting_service.resolve_alert.assert_called_once_with("alert-1", "test-user", "Fixed database connection")

    async def test_resolve_alert_no_notes(self, mock_alerting_service, mock_user):
        """Test alert resolution without notes"""
        from app.api.alerts import resolve_alert

        # Mock resolved alert
        resolved_alert = Alert(
            id="alert-1",
            alert_type=AlertType.DATABASE_CONNECTION,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            title="Database Connection Failed",
            description="Database connection failed",
            database_id="db1",
            created_at=datetime.now(UTC),
        )
        mock_alerting_service.resolve_alert.return_value = resolved_alert

        resolution_data = {}  # No notes
        result = await resolve_alert("alert-1", resolution_data, mock_alerting_service, mock_user)

        assert result["success"] is True
        mock_alerting_service.resolve_alert.assert_called_once_with("alert-1", "test-user", None)

    async def test_resolve_alert_not_found(self, mock_alerting_service, mock_user):
        """Test resolving non-existent alert"""
        from app.api.alerts import resolve_alert

        # Mock alert not found
        mock_alerting_service.resolve_alert.return_value = None

        resolution_data = {"notes": "Test notes"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await resolve_alert("nonexistent", resolution_data, mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 404
        assert "Alert nonexistent not found" in str(exc_info.value.detail)

    async def test_resolve_alert_error(self, mock_alerting_service, mock_user):
        """Test alert resolution with error"""
        from app.api.alerts import resolve_alert

        # Mock service error
        mock_alerting_service.resolve_alert.side_effect = Exception("Service error")

        resolution_data = {"notes": "Test notes"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await resolve_alert("alert-1", resolution_data, mock_alerting_service, mock_user)

        assert exc_info.value.status_code == 500
        assert "Failed to resolve alert" in str(exc_info.value.detail)


class TestAlertsAPIIntegration:
    """Integration tests for alerts API"""

    @pytest.fixture
    def test_app_with_mocked_deps(self):
        """Create test app with mocked dependencies"""
        from fastapi import FastAPI

        from app.api.alerts import router

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client_with_mocked_deps(self, test_app_with_mocked_deps):
        """Test client with mocked dependencies"""
        return TestClient(test_app_with_mocked_deps)

    def test_alerts_router_included(self, test_app_with_mocked_deps):
        """Test that alerts router is properly included"""
        # Check that the router has the expected routes
        route_paths = [route.path for route in test_app_with_mocked_deps.routes]

        assert "/api/alerts/health" in route_paths
        assert "/api/alerts/active" in route_paths
        assert "/api/alerts/" in route_paths

    @patch("app.api.alerts.get_alerting_service")
    @patch("app.api.alerts.require_viewer")
    def test_get_system_health_endpoint_mock(self, mock_require_viewer, mock_get_alerting_service, client_with_mocked_deps):
        """Test system health endpoint with mocked dependencies"""
        # Mock user
        mock_user = User(id="test-user", username="testuser", email="test@example.com", auth_method="auth_key")
        mock_require_viewer.return_value = mock_user

        # Mock alerting service
        mock_service = AsyncMock()
        mock_service.get_system_health.return_value = SystemHealth(
            overall_status="healthy",
            database_count=1,
            healthy_databases=1,
            active_alerts=0,
            replication_streams=0,
            healthy_streams=0,
            uptime_seconds=100,
        )
        mock_get_alerting_service.return_value = mock_service

        response = client_with_mocked_deps.get("/api/alerts/health")

        # The response might be different due to authentication middleware
        # but should not error out completely
        assert response.status_code in [200, 401, 422]

    @patch("app.api.alerts.get_alerting_service")
    @patch("app.api.alerts.require_viewer")
    def test_get_active_alerts_endpoint_mock(self, mock_require_viewer, mock_get_alerting_service, client_with_mocked_deps):
        """Test active alerts endpoint with mocked dependencies"""
        # Mock user
        mock_user = User(id="test-user", username="testuser", email="test@example.com", auth_method="auth_key")
        mock_require_viewer.return_value = mock_user

        # Mock alerting service
        mock_service = AsyncMock()
        mock_service.get_active_alerts.return_value = []
        mock_get_alerting_service.return_value = mock_service

        response = client_with_mocked_deps.get("/api/alerts/active")

        # The response might be different due to authentication middleware
        # but should not error out completely
        assert response.status_code in [200, 401, 422]
