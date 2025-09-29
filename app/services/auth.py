"""
Authentication service handling multiple authentication methods
"""
import json
import os
import secrets
from datetime import datetime, timedelta

import boto3
import redis.asyncio as redis
from fastapi import Request

from app.models.auth import (
    AuthConfig,
    LoginRequest,
    LoginResponse,
    OIDCTokenResponse,
    OIDCUserInfo,
    User,
    UserSession,
)


class AuthenticationService:
    """Service for handling authentication across multiple methods"""

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.secrets_client = boto3.client("secretsmanager")
        self._auth_config: AuthConfig | None = None

    async def get_auth_config(self) -> AuthConfig:
        """Get authentication configuration from Redis or create default"""
        if self._auth_config is None:
            try:
                config_data = await self.redis_client.get("auth:config")
                if config_data:
                    self._auth_config = AuthConfig.model_validate_json(config_data)
                else:
                    # Create default configuration
                    self._auth_config = AuthConfig()
                    await self.save_auth_config(self._auth_config)
            except Exception:
                # Fallback to default config if Redis is unavailable
                self._auth_config = AuthConfig()
        return self._auth_config

    async def save_auth_config(self, config: AuthConfig) -> None:
        """Save authentication configuration to Redis"""
        config.updated_at = datetime.utcnow()
        await self.redis_client.set("auth:config", config.model_dump_json())
        self._auth_config = config

    async def authenticate_user(self, login_request: LoginRequest, request: Request) -> LoginResponse:
        """Authenticate user using specified method"""
        try:
            if login_request.auth_method == "secrets_manager":
                return await self._authenticate_secrets_manager(login_request, request)
            elif login_request.auth_method == "auth_key":
                return await self._authenticate_auth_key(login_request, request)
            else:
                return LoginResponse(
                    success=False,
                    error_message=f"Unsupported authentication method: {login_request.auth_method}",
                )
        except Exception as e:
            return LoginResponse(
                success=False,
                error_message=f"Authentication failed: {str(e)}",
            )

    async def _authenticate_secrets_manager(self, login_request: LoginRequest, request: Request) -> LoginResponse:
        """Authenticate using Secrets Manager stored credentials"""
        config = await self.get_auth_config()

        if not config.secrets_manager_enabled:
            return LoginResponse(
                success=False,
                error_message="Secrets Manager authentication is disabled",
            )

        if not login_request.username or not login_request.password:
            return LoginResponse(
                success=False,
                error_message="Username and password are required for Secrets Manager authentication",
            )

        if not config.user_credentials_secret_arn:
            return LoginResponse(
                success=False,
                error_message="User credentials secret ARN not configured",
            )

        try:
            # Retrieve user credentials from Secrets Manager
            response = self.secrets_client.get_secret_value(SecretId=config.user_credentials_secret_arn)
            credentials = json.loads(response["SecretString"])

            # Check if user exists and password matches
            user_key = f"user:{login_request.username}"
            if user_key not in credentials:
                return LoginResponse(
                    success=False,
                    error_message="Invalid username or password",
                )

            user_data = credentials[user_key]
            if user_data.get("password") != login_request.password:
                return LoginResponse(
                    success=False,
                    error_message="Invalid username or password",
                )

            # Create or update user
            user = User(
                username=login_request.username,
                email=user_data.get("email"),
                full_name=user_data.get("full_name"),
                auth_method="secrets_manager",
                roles=user_data.get("roles", []),
                permissions=user_data.get("permissions", []),
                is_admin=user_data.get("is_admin", False),
                last_login=datetime.utcnow(),
            )

            # Create session
            session = await self._create_session(user, request)

            return LoginResponse(
                success=True,
                session_id=session.session_id,
                user=user,
            )

        except Exception as e:
            return LoginResponse(
                success=False,
                error_message=f"Failed to authenticate with Secrets Manager: {str(e)}",
            )

    async def _authenticate_auth_key(self, login_request: LoginRequest, request: Request) -> LoginResponse:
        """Authenticate using simple auth key"""
        config = await self.get_auth_config()

        if not config.auth_key_enabled:
            return LoginResponse(
                success=False,
                error_message="Auth key authentication is disabled",
            )

        if not login_request.auth_key:
            return LoginResponse(
                success=False,
                error_message="Auth key is required",
            )

        # Get auth key from environment
        expected_auth_key = os.getenv(config.auth_key_env_var)
        if not expected_auth_key:
            return LoginResponse(
                success=False,
                error_message="Auth key not configured on server",
            )

        if not secrets.compare_digest(login_request.auth_key, expected_auth_key):
            return LoginResponse(
                success=False,
                error_message="Invalid auth key",
            )

        # Create admin user for auth key authentication
        user = User(
            username="admin",
            full_name="Administrator",
            auth_method="auth_key",
            roles=["admin"],
            is_admin=True,
            last_login=datetime.utcnow(),
        )

        # Create session
        session = await self._create_session(user, request)

        return LoginResponse(
            success=True,
            session_id=session.session_id,
            user=user,
        )

    async def authenticate_oidc_callback(self, code: str, state: str, request: Request) -> LoginResponse:
        """Handle OIDC callback and authenticate user"""
        config = await self.get_auth_config()

        if not config.iam_identity_center_enabled:
            return LoginResponse(
                success=False,
                error_message="IAM Identity Center authentication is disabled",
            )

        try:
            # Exchange code for tokens
            token_response = await self._exchange_oidc_code(code, config)

            # Get user information from ID token
            user_info = await self._get_oidc_user_info(token_response, config)

            # Validate user domain if configured
            if config.allowed_domains and user_info.email:
                domain = user_info.email.split("@")[-1]
                if domain not in config.allowed_domains:
                    return LoginResponse(
                        success=False,
                        error_message=f"Email domain {domain} is not allowed",
                    )

            # Create or update user
            user = User(
                username=user_info.preferred_username or user_info.sub,
                email=user_info.email,
                full_name=user_info.name,
                auth_method="iam_identity_center",
                iam_user_id=user_info.sub,
                iam_groups=user_info.groups,
                roles=self._map_groups_to_roles(user_info.groups),
                is_admin=self._is_admin_user(user_info.groups),
                last_login=datetime.utcnow(),
            )

            # Create session
            session = await self._create_session(user, request)

            return LoginResponse(
                success=True,
                session_id=session.session_id,
                user=user,
            )

        except Exception as e:
            return LoginResponse(
                success=False,
                error_message=f"OIDC authentication failed: {str(e)}",
            )

    async def _exchange_oidc_code(self, code: str, config: AuthConfig) -> OIDCTokenResponse:
        """Exchange OIDC authorization code for tokens"""
        # This would typically make an HTTP request to the token endpoint
        # For now, we'll simulate the response
        # In a real implementation, you'd use httpx or similar to make the request

        # Placeholder implementation
        return OIDCTokenResponse(
            access_token="mock_access_token",
            expires_in=3600,
            id_token="mock_id_token",
        )

    async def _get_oidc_user_info(self, token_response: OIDCTokenResponse, config: AuthConfig) -> OIDCUserInfo:
        """Get user information from OIDC provider"""
        # This would typically decode the ID token or call the userinfo endpoint
        # For now, we'll simulate the response

        # Placeholder implementation
        return OIDCUserInfo(
            sub="mock_user_id",
            email="admin@example.com",
            name="Mock Admin User",
            preferred_username="admin",
            groups=["administrators"],
        )

    def _map_groups_to_roles(self, groups: list[str]) -> list[str]:
        """Map IAM groups to application roles"""
        role_mapping = {
            "administrators": ["admin"],
            "database_admins": ["db_admin"],
            "read_only": ["viewer"],
        }

        roles = []
        for group in groups:
            if group in role_mapping:
                roles.extend(role_mapping[group])

        return list(set(roles))  # Remove duplicates

    def _is_admin_user(self, groups: list[str]) -> bool:
        """Check if user should have admin privileges"""
        admin_groups = {"administrators", "database_admins"}
        return bool(set(groups) & admin_groups)

    async def _create_session(self, user: User, request: Request) -> UserSession:
        """Create a new user session"""
        config = await self.get_auth_config()

        # Clean up old sessions for user
        await self._cleanup_user_sessions(user.id, config.max_sessions_per_user)

        # Create new session
        session = UserSession(
            user_id=user.id,
            auth_method=user.auth_method,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            expires_at=datetime.utcnow() + timedelta(hours=config.session_timeout_hours),
        )

        # Store user and session in Redis
        await user.save_to_redis(self.redis_client, "user")
        await session.save_to_redis(self.redis_client, f"user_session:{user.id}")

        # Store session mapping
        await self.redis_client.set(
            f"session:{session.session_id}",
            user.id,  # Store user ID for lookup
            ex=int(timedelta(hours=config.session_timeout_hours).total_seconds()),
        )

        return session

    async def _cleanup_user_sessions(self, user_id: str, max_sessions: int) -> None:
        """Clean up old sessions for a user"""
        # Get all sessions for user
        pattern = f"user_session:{user_id}:*"
        session_keys = []

        try:
            # Use scan_iter properly
            scan_iter = self.redis_client.scan_iter(match=pattern)
            async for key in scan_iter:
                session_keys.append(key)
        except Exception:
            # If scan_iter fails, continue without cleanup
            return

        if len(session_keys) >= max_sessions:
            # Sort by creation time and remove oldest
            sessions = []
            for key in session_keys:
                session_data = await self.redis_client.get(key)
                if session_data:
                    session = UserSession.model_validate_json(session_data)
                    sessions.append((session.created_at, key, session.session_id))

            sessions.sort()  # Sort by creation time

            # Remove oldest sessions
            for _, key, session_id in sessions[: -(max_sessions - 1)]:
                await self.redis_client.delete(key)
                await self.redis_client.delete(f"session:{session_id}")

    async def get_session(self, session_id: str) -> UserSession | None:
        """Get session by ID"""
        try:
            session_key = await self.redis_client.get(f"session:{session_id}")
            if not session_key:
                return None

            session_data = await self.redis_client.get(f"pgrepman:user_session:{session_key}:{session_id}")
            if not session_data:
                return None

            session = UserSession.model_validate_json(session_data)

            # Check if session is expired
            if session.is_expired():
                await self.logout_session(session_id)
                return None

            return session
        except Exception:
            return None

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID"""
        try:
            return await User.load_from_redis(self.redis_client, user_id, "user")
        except Exception:
            return None

    async def logout_session(self, session_id: str) -> bool:
        """Logout a session"""
        try:
            session = await self.get_session(session_id)
            if not session:
                return False

            # Remove session data
            await self.redis_client.delete(f"session:{session_id}")
            await self.redis_client.delete(f"user_session:{session.user_id}:{session_id}")

            return True
        except Exception:
            return False

    async def extend_session(self, session_id: str) -> bool:
        """Extend session expiration"""
        try:
            session = await self.get_session(session_id)
            if not session:
                return False

            config = await self.get_auth_config()
            session.extend_session(config.session_timeout_hours)

            # Update session in Redis
            await session.save_to_redis(self.redis_client)

            # Update session mapping expiration
            await self.redis_client.expire(
                f"session:{session_id}",
                int(timedelta(hours=config.session_timeout_hours).total_seconds()),
            )

            return True
        except Exception:
            return False

    def get_oidc_authorization_url(self, config: AuthConfig) -> str:
        """Generate OIDC authorization URL"""
        if not config.iam_identity_center_enabled or not config.iam_issuer_url:
            raise ValueError("IAM Identity Center not configured")

        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)

        # Build authorization URL
        params = {
            "response_type": "code",
            "client_id": config.iam_client_id,
            "redirect_uri": config.iam_redirect_uri,
            "scope": "openid email profile",
            "state": state,
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{config.iam_issuer_url}/authorize?{query_string}"
