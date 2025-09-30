"""
FastAPI authentication middleware
"""

from collections.abc import Callable

import redis.asyncio as redis
from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.models.auth import User, UserSession
from app.services.auth import AuthenticationService


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for handling authentication across all requests"""

    def __init__(self, app, redis_client: redis.Redis):
        super().__init__(app)
        self.redis_client = redis_client
        self.auth_service = AuthenticationService(redis_client)

        # Public endpoints that don't require authentication
        self.public_endpoints = {
            "/",
            "/health",
            "/api/auth/login",
            "/api/auth/oidc/authorize",
            "/api/auth/oidc/callback",
            "/docs",
            "/openapi.json",
            "/redoc",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and handle authentication"""

        # Skip authentication for public endpoints
        if self._is_public_endpoint(request.url.path):
            return await call_next(request)

        # Skip authentication for static files
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        # Try to authenticate the request
        user, session = await self._authenticate_request(request)

        if not user or not session:
            # Return 401 for API endpoints, redirect for web interface
            if request.url.path.startswith("/api/"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                # Redirect to login page for web interface
                from fastapi.responses import RedirectResponse

                return RedirectResponse(url="/login", status_code=302)

        # Add user and session to request state
        request.state.user = user
        request.state.session = session

        # Extend session on activity
        await self.auth_service.extend_session(session.session_id)

        return await call_next(request)

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public (doesn't require authentication)"""
        return path in self.public_endpoints or path.startswith("/login")

    async def _authenticate_request(self, request: Request) -> tuple[User | None, UserSession | None]:
        """Authenticate request using session cookie or Authorization header"""

        # Try session cookie first
        session_id = request.cookies.get("session_id")
        if session_id:
            session = await self.auth_service.get_session(session_id)
            if session:
                user = await self.auth_service.get_user(session.user_id)
                if user and user.is_active:
                    return user, session

        # Try Authorization header for API requests
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            session = await self.auth_service.get_session(token)
            if session:
                user = await self.auth_service.get_user(session.user_id)
                if user and user.is_active:
                    return user, session

        return None, None


class RequireRole:
    """Dependency for requiring specific roles"""

    def __init__(self, required_roles: list[str]):
        self.required_roles = required_roles

    def __call__(self, request: Request) -> User:
        """Check if user has required roles"""
        user: User = getattr(request.state, "user", None)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        # Check if user has any of the required roles
        if self.required_roles and not any(role in user.roles for role in self.required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(self.required_roles)}",
            )

        return user


class RequireAdmin:
    """Dependency for requiring admin privileges"""

    def __call__(self, request: Request) -> User:
        """Check if user has admin privileges"""
        user: User = getattr(request.state, "user", None)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        if not user.is_admin and "admin" not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )

        return user


# Dependency instances
require_admin = RequireAdmin()
require_db_admin = RequireRole(["admin", "db_admin"])
require_viewer = RequireRole(["admin", "db_admin", "viewer"])


def get_current_user(request: Request) -> User:
    """Get current authenticated user"""
    user: User = getattr(request.state, "user", None)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return user


def get_current_session(request: Request) -> UserSession:
    """Get current user session"""
    session: UserSession = getattr(request.state, "session", None)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid session required",
        )

    return session
