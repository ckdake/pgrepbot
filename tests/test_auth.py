"""
Tests for authentication system
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

# Test app is provided by conftest.py fixture
from app.models.auth import AuthConfig, LoginRequest, User, UserSession
from app.services.auth import AuthenticationService


class TestAuthenticationModels:
    """Test authentication models"""

    def test_user_model_validation(self):
        """Test User model validation"""
        user = User(
            username="test_user",
            email="test@example.com",
            full_name="Test User",
            auth_method="secrets_manager",
            roles=["viewer"],
            is_admin=False,
        )

        assert user.username == "test_user"
        assert user.email == "test@example.com"
        assert user.auth_method == "secrets_manager"
        assert "viewer" in user.roles
        assert not user.is_admin

    def test_user_username_validation(self):
        """Test username validation"""
        # Valid usernames
        valid_usernames = ["test", "test_user", "test-user", "test.user", "user123"]
        for username in valid_usernames:
            user = User(username=username, auth_method="auth_key")
            assert user.username == username.lower()

        # Invalid usernames should raise validation error
        with pytest.raises(ValueError, match="Username must contain only"):
            User(username="test@user", auth_method="auth_key")

    def test_user_session_model(self):
        """Test UserSession model"""
        session = UserSession(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            auth_method="secrets_manager",
            ip_address="192.168.1.1",
        )

        assert session.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert session.auth_method == "secrets_manager"
        assert session.is_active
        assert not session.is_expired()

    def test_user_session_uuid_validation(self):
        """Test user session UUID validation"""
        with pytest.raises(ValueError, match="User ID must be a valid UUID"):
            UserSession(user_id="invalid-uuid", auth_method="auth_key")

    def test_auth_config_model(self):
        """Test AuthConfig model"""
        config = AuthConfig(
            iam_identity_center_enabled=True,
            secrets_manager_enabled=True,
            auth_key_enabled=False,
            session_timeout_hours=12,
        )

        assert config.iam_identity_center_enabled
        assert config.secrets_manager_enabled
        assert not config.auth_key_enabled
        assert config.session_timeout_hours == 12

    def test_login_request_model(self):
        """Test LoginRequest model"""
        # Secrets manager login
        login_req = LoginRequest(
            auth_method="secrets_manager",
            username="testuser",
            password="testpass",
        )
        assert login_req.auth_method == "secrets_manager"
        assert login_req.username == "testuser"

        # Auth key login
        auth_key_req = LoginRequest(
            auth_method="auth_key",
            auth_key="secret-key-123",
        )
        assert auth_key_req.auth_method == "auth_key"
        assert auth_key_req.auth_key == "secret-key-123"


class TestAuthenticationService:
    """Test authentication service"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        redis_mock.ping.return_value = True
        return redis_mock

    @pytest.fixture
    def auth_service(self, mock_redis):
        """Create authentication service with mocked Redis"""
        return AuthenticationService(mock_redis)

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request"""
        request = MagicMock(spec=Request)
        request.client.host = "127.0.0.1"
        request.headers = {"user-agent": "test-client"}
        return request

    @pytest.mark.asyncio
    async def test_get_auth_config_default(self, auth_service, mock_redis):
        """Test getting default auth config"""
        mock_redis.get.return_value = None

        config = await auth_service.get_auth_config()

        assert isinstance(config, AuthConfig)
        assert config.secrets_manager_enabled
        assert config.auth_key_enabled
        assert not config.iam_identity_center_enabled

    @pytest.mark.asyncio
    async def test_auth_key_authentication_success(self, auth_service, mock_request):
        """Test successful auth key authentication"""
        with patch.dict(os.environ, {"AUTH_KEY": "test-key-123"}):
            login_request = LoginRequest(
                auth_method="auth_key",
                auth_key="test-key-123",
            )

            response = await auth_service.authenticate_user(login_request, mock_request)

            assert response.success
            assert response.session_id is not None
            assert response.user is not None
            assert response.user.username == "admin"
            assert response.user.is_admin

    @pytest.mark.asyncio
    async def test_auth_key_authentication_failure(self, auth_service, mock_request):
        """Test failed auth key authentication"""
        with patch.dict(os.environ, {"AUTH_KEY": "correct-key"}):
            login_request = LoginRequest(
                auth_method="auth_key",
                auth_key="wrong-key",
            )

            response = await auth_service.authenticate_user(login_request, mock_request)

            assert not response.success
            assert "Invalid auth key" in response.error_message

    @pytest.mark.asyncio
    async def test_secrets_manager_authentication_missing_credentials(self, auth_service, mock_request):
        """Test secrets manager authentication with missing credentials"""
        login_request = LoginRequest(
            auth_method="secrets_manager",
            username="testuser",
            # Missing password
        )

        response = await auth_service.authenticate_user(login_request, mock_request)

        assert not response.success
        assert "Username and password are required" in response.error_message

    @pytest.mark.asyncio
    async def test_unsupported_auth_method(self, auth_service, mock_request):
        """Test unsupported authentication method"""
        # This would require modifying the LoginRequest model to allow invalid methods
        # For now, we'll test the service directly
        login_request = MagicMock()
        login_request.auth_method = "unsupported_method"

        response = await auth_service.authenticate_user(login_request, mock_request)

        assert not response.success
        assert "Unsupported authentication method" in response.error_message


class TestAuthenticationAPI:
    """Test authentication API endpoints"""

    def test_login_endpoint_exists(self, client):
        """Test that login endpoint exists"""
        # Test that the endpoint exists (even if it fails due to missing Redis)
        response = client.post("/api/auth/login", json={"auth_method": "auth_key", "auth_key": "test"})

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_auth_methods_endpoint_exists(self, client):
        """Test that auth methods endpoint exists"""
        response = client.get("/api/auth/methods")

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_login_page_exists(self, client):
        """Test that login page exists"""
        response = client.get("/login")

        assert response.status_code == 200
        assert "PostgreSQL Replication Manager" in response.text
        assert "login-container" in response.text


class TestAuthenticationIntegration:
    """Integration tests for authentication system"""

    @pytest.mark.asyncio
    async def test_full_auth_key_flow(self):
        """Test complete auth key authentication flow"""
        # This would require a more complex setup with actual Redis
        # For now, we'll test the components individually
        pass

    def test_login_page_renders(self, client):
        """Test that login page renders correctly"""
        response = client.get("/login")

        assert response.status_code == 200
        assert "Sign in with AWS IAM Identity Center" in response.text
        assert "Username" in response.text
        assert "Authentication Key" in response.text
