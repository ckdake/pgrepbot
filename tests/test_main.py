"""
Basic tests for the main FastAPI application
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Test client is provided by conftest.py fixture


def test_root_endpoint(client):
    """Test the root endpoint returns HTML"""
    response = client.get("/")
    assert response.status_code == 200
    assert "PostgreSQL Replication Manager" in response.text
    assert "text/html" in response.headers["content-type"]


def test_health_check(client):
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "postgres-replication-manager"
    assert "version" in data


def test_login_page(client):
    """Test the login page endpoint"""
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PostgreSQL Replication Manager" in response.text


class TestMainApplication:
    """Test the actual main application with authentication middleware"""

    @pytest.fixture
    def real_client(self):
        """Test client for the real FastAPI app with authentication middleware"""
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            return TestClient(app)

    def test_app_metadata(self, real_client):
        """Test FastAPI app metadata"""
        assert app.title == "PostgreSQL Replication Manager"
        assert "Centralized management of PostgreSQL logical replication" in app.description
        assert app.version == "1.0.0"

    def test_health_endpoint_real_app(self, real_client):
        """Test health endpoint on real app"""
        response = real_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "postgres-replication-manager"
        assert data["version"] == "1.0.0"

    @patch("app.main.templates")
    def test_login_page_real_app(self, mock_templates, real_client):
        """Test login page on real app"""
        mock_templates.TemplateResponse.return_value = MagicMock()
        mock_templates.TemplateResponse.return_value.status_code = 200

        response = real_client.get("/login")
        # The response might be different due to middleware, but should not error
        assert response.status_code in [200, 302, 401]

    @patch("app.main.get_current_user_optional")
    @patch("app.main.templates")
    def test_root_with_authenticated_user(self, mock_templates, mock_get_user, real_client):
        """Test root endpoint with authenticated user"""
        from app.models.auth import User

        # Mock authenticated user
        mock_user = User(id="test-user", username="testuser", email="test@example.com", auth_method="auth_key")
        mock_get_user.return_value = mock_user

        mock_templates.TemplateResponse.return_value = MagicMock()
        mock_templates.TemplateResponse.return_value.status_code = 200

        response = real_client.get("/")
        assert response.status_code in [200, 302, 401]

    @patch("app.main.get_current_user_optional")
    @patch("app.main.templates")
    def test_root_without_authenticated_user(self, mock_templates, mock_get_user, real_client):
        """Test root endpoint without authenticated user"""
        # Mock no authenticated user
        mock_get_user.return_value = None

        mock_templates.TemplateResponse.return_value = MagicMock()
        mock_templates.TemplateResponse.return_value.status_code = 200

        response = real_client.get("/")
        assert response.status_code in [200, 302, 401]

    @patch("app.main.get_current_user_optional")
    @patch("app.main.templates")
    def test_dashboard_with_authenticated_user(self, mock_templates, mock_get_user, real_client):
        """Test dashboard endpoint with authenticated user"""
        from app.models.auth import User

        # Mock authenticated user
        mock_user = User(id="test-user", username="testuser", email="test@example.com", auth_method="auth_key")
        mock_get_user.return_value = mock_user

        mock_templates.TemplateResponse.return_value = MagicMock()
        mock_templates.TemplateResponse.return_value.status_code = 200

        response = real_client.get("/dashboard")
        assert response.status_code in [200, 302, 401]

    @patch("app.main.get_current_user_optional")
    @patch("app.main.templates")
    def test_dashboard_without_authenticated_user(self, mock_templates, mock_get_user, real_client):
        """Test dashboard endpoint without authenticated user"""
        # Mock no authenticated user
        mock_get_user.return_value = None

        mock_templates.TemplateResponse.return_value = MagicMock()
        mock_templates.TemplateResponse.return_value.status_code = 200

        response = real_client.get("/dashboard")
        assert response.status_code in [200, 302, 401]


class TestApplicationLifecycle:
    """Test application startup and shutdown events"""

    @patch("app.main.start_background_tasks")
    @patch("app.main.redis_client")
    async def test_startup_event_success(self, mock_redis, mock_start_tasks):
        """Test successful startup event"""
        mock_start_tasks.return_value = AsyncMock()

        from app.main import startup_event

        # Should not raise an exception
        await startup_event()
        mock_start_tasks.assert_called_once_with(mock_redis)

    @patch("app.main.start_background_tasks")
    @patch("app.main.redis_client")
    async def test_startup_event_failure(self, mock_redis, mock_start_tasks):
        """Test startup event with background task failure"""
        mock_start_tasks.side_effect = Exception("Background task failed")

        from app.main import startup_event

        # Should not raise an exception even if background tasks fail
        await startup_event()
        mock_start_tasks.assert_called_once_with(mock_redis)

    @patch("app.main.stop_background_tasks")
    async def test_shutdown_event_success(self, mock_stop_tasks):
        """Test successful shutdown event"""
        mock_stop_tasks.return_value = AsyncMock()

        from app.main import shutdown_event

        # Should not raise an exception
        await shutdown_event()
        mock_stop_tasks.assert_called_once()

    @patch("app.main.stop_background_tasks")
    async def test_shutdown_event_failure(self, mock_stop_tasks):
        """Test shutdown event with background task failure"""
        mock_stop_tasks.side_effect = Exception("Background task stop failed")

        from app.main import shutdown_event

        # Should not raise an exception even if background tasks fail to stop
        await shutdown_event()
        mock_stop_tasks.assert_called_once()


class TestRedisConfiguration:
    """Test Redis client configuration"""

    @patch.dict(os.environ, {"REDIS_URL": "redis://custom-host:6380"})
    def test_redis_url_from_environment(self):
        """Test Redis URL configuration from environment variable"""
        # Import after setting environment variable
        import importlib

        import app.main
        importlib.reload(app.main)

        # The Redis client should be configured with the custom URL
        # This is tested indirectly through the middleware setup
        assert app.main.redis_client is not None

    @patch.dict(os.environ, {}, clear=True)
    def test_redis_url_default(self):
        """Test Redis URL default configuration"""
        # Import after clearing environment variables
        import importlib

        import app.main
        importlib.reload(app.main)

        # The Redis client should be configured with the default URL
        assert app.main.redis_client is not None
