"""
Authentication and authorization models
"""
import uuid
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Custom datetime serializer
from app.models.migration import DatetimeSerializer, OptionalDatetimeSerializer
from app.utils.redis_serializer import RedisModelMixin


class User(BaseModel, RedisModelMixin):
    """User model for authentication and authorization"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str = Field(..., min_length=1, max_length=255)
    email: str | None = Field(None, description="User email address")
    full_name: str | None = Field(None, description="User's full name")

    # Authentication method used
    auth_method: Literal["iam_identity_center", "secrets_manager", "auth_key"] = Field(...)

    # IAM Identity Center specific fields
    iam_user_id: str | None = Field(None, description="IAM Identity Center user ID")
    iam_groups: list[str] = Field(default_factory=list, description="IAM groups")

    # Role-based access control
    roles: list[str] = Field(default_factory=list, description="User roles")
    permissions: list[str] = Field(default_factory=list, description="Specific permissions")

    # Account status
    is_active: bool = Field(default=True, description="Whether user account is active")
    is_admin: bool = Field(default=False, description="Whether user has admin privileges")

    # Timestamps
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    last_login: OptionalDatetimeSerializer = Field(None, description="Last login timestamp")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format"""
        if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Username must contain only alphanumeric characters, hyphens, underscores, and dots")
        return v.lower()


class UserSession(BaseModel, RedisModelMixin):
    """User session model for session management"""

    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="User ID associated with session")
    auth_method: Literal["iam_identity_center", "secrets_manager", "auth_key"] = Field(...)

    # Session metadata
    ip_address: str | None = Field(None, description="Client IP address")
    user_agent: str | None = Field(None, description="Client user agent")

    # Session timing
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    expires_at: DatetimeSerializer = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=24)
    )
    last_activity: DatetimeSerializer = Field(default_factory=datetime.utcnow)

    # Session status
    is_active: bool = Field(default=True, description="Whether session is active")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Validate user ID is UUID"""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("User ID must be a valid UUID") from None
        return v

    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at

    def extend_session(self, hours: int = 24) -> None:
        """Extend session expiration"""
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
        self.last_activity = datetime.utcnow()


class AuthConfig(BaseModel, RedisModelMixin):
    """Authentication configuration model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    # IAM Identity Center configuration
    iam_identity_center_enabled: bool = Field(default=False)
    iam_issuer_url: str | None = Field(None, description="OIDC issuer URL")
    iam_client_id: str | None = Field(None, description="OIDC client ID")
    iam_client_secret_arn: str | None = Field(None, description="Secrets Manager ARN for client secret")
    iam_redirect_uri: str | None = Field(None, description="OIDC redirect URI")

    # Secrets Manager authentication configuration
    secrets_manager_enabled: bool = Field(default=True)
    user_credentials_secret_arn: str | None = Field(
        None, description="Secrets Manager ARN containing user credentials"
    )

    # Auth key configuration
    auth_key_enabled: bool = Field(default=True)
    auth_key_env_var: str = Field(default="AUTH_KEY", description="Environment variable name for auth key")

    # Session configuration
    session_timeout_hours: int = Field(default=24, ge=1, le=168)  # 1 hour to 1 week
    max_sessions_per_user: int = Field(default=5, ge=1, le=50)

    # Security settings
    require_https: bool = Field(default=True, description="Require HTTPS for authentication")
    allowed_domains: list[str] = Field(
        default_factory=list, description="Allowed email domains for IAM Identity Center"
    )

    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    updated_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)


class LoginRequest(BaseModel):
    """Login request model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    auth_method: Literal["secrets_manager", "auth_key"] = Field(...)
    username: str | None = Field(None, description="Username for secrets manager auth")
    password: str | None = Field(None, description="Password for secrets manager auth")
    auth_key: str | None = Field(None, description="Auth key for simple authentication")


class LoginResponse(BaseModel):
    """Login response model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    success: bool = Field(..., description="Whether login was successful")
    session_id: str | None = Field(None, description="Session ID if successful")
    user: User | None = Field(None, description="User information if successful")
    error_message: str | None = Field(None, description="Error message if failed")
    redirect_url: str | None = Field(None, description="Redirect URL for OIDC flow")


class OIDCTokenResponse(BaseModel):
    """OIDC token response model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    access_token: str = Field(..., description="Access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    refresh_token: str | None = Field(None, description="Refresh token")
    id_token: str | None = Field(None, description="ID token")
    scope: str | None = Field(None, description="Token scope")


class OIDCUserInfo(BaseModel):
    """OIDC user information model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    sub: str = Field(..., description="Subject identifier")
    email: str | None = Field(None, description="User email")
    name: str | None = Field(None, description="User full name")
    preferred_username: str | None = Field(None, description="Preferred username")
    groups: list[str] = Field(default_factory=list, description="User groups")
