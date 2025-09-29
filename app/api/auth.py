"""
Authentication API endpoints
"""
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_redis_client
from app.middleware.auth import get_current_session, get_current_user
from app.models.auth import AuthConfig, LoginRequest, LoginResponse, User, UserSession
from app.services.auth import AuthenticationService

router = APIRouter(prefix="/api/auth", tags=["authentication"])




async def get_auth_service(redis_client: redis.Redis = Depends(get_redis_client)) -> AuthenticationService:
    """Get authentication service"""
    return AuthenticationService(redis_client)


@router.post("/login", response_model=LoginResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Login with username/password or auth key"""

    login_response = await auth_service.authenticate_user(login_request, request)

    if login_response.success and login_response.session_id:
        # Set session cookie
        response.set_cookie(
            key="session_id",
            value=login_response.session_id,
            httponly=True,
            secure=True,  # Should be True in production with HTTPS
            samesite="lax",
            max_age=24 * 60 * 60,  # 24 hours
        )

    return login_response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: UserSession = Depends(get_current_session),
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Logout current session"""

    success = await auth_service.logout_session(session.session_id)

    # Clear session cookie
    response.delete_cookie(key="session_id")

    return {"success": success, "message": "Logged out successfully"}


@router.get("/me", response_model=User)
async def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current user information"""
    return user


@router.get("/session", response_model=UserSession)
async def get_current_session_info(session: UserSession = Depends(get_current_session)):
    """Get current session information"""
    return session


@router.get("/oidc/authorize")
async def oidc_authorize(
    request: Request,
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Initiate OIDC authorization flow"""

    config = await auth_service.get_auth_config()

    if not config.iam_identity_center_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IAM Identity Center authentication is not enabled",
        )

    try:
        authorization_url = auth_service.get_oidc_authorization_url(config)
        return RedirectResponse(url=authorization_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/oidc/callback")
async def oidc_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Handle OIDC callback"""

    login_response = await auth_service.authenticate_oidc_callback(code, state, request)

    if login_response.success and login_response.session_id:
        # Set session cookie
        response.set_cookie(
            key="session_id",
            value=login_response.session_id,
            httponly=True,
            secure=True,  # Should be True in production with HTTPS
            samesite="lax",
            max_age=24 * 60 * 60,  # 24 hours
        )

        # Redirect to main application
        return RedirectResponse(url="/", status_code=302)
    else:
        # Redirect to login with error
        error_msg = login_response.error_message or "Authentication failed"
        return RedirectResponse(url=f"/login?error={error_msg}", status_code=302)


@router.get("/config", response_model=AuthConfig)
async def get_auth_config(
    user: User = Depends(get_current_user),
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Get authentication configuration (admin only)"""

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    return await auth_service.get_auth_config()


@router.put("/config", response_model=AuthConfig)
async def update_auth_config(
    config: AuthConfig,
    user: User = Depends(get_current_user),
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Update authentication configuration (admin only)"""

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    await auth_service.save_auth_config(config)
    return config


@router.get("/methods")
async def get_available_auth_methods(
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Get available authentication methods"""

    config = await auth_service.get_auth_config()

    methods = []

    if config.iam_identity_center_enabled:
        methods.append({
            "method": "iam_identity_center",
            "name": "AWS IAM Identity Center",
            "description": "Single sign-on with AWS IAM Identity Center",
            "primary": True,
        })

    if config.secrets_manager_enabled:
        methods.append({
            "method": "secrets_manager",
            "name": "Username/Password",
            "description": "Login with username and password stored in AWS Secrets Manager",
            "primary": not config.iam_identity_center_enabled,
        })

    if config.auth_key_enabled:
        methods.append({
            "method": "auth_key",
            "name": "Auth Key",
            "description": "Simple authentication using a shared key",
            "primary": not config.iam_identity_center_enabled and not config.secrets_manager_enabled,
        })

    return {"methods": methods}


@router.post("/extend-session")
async def extend_session(
    session: UserSession = Depends(get_current_session),
    auth_service: AuthenticationService = Depends(get_auth_service),
):
    """Extend current session"""

    success = await auth_service.extend_session(session.session_id)

    return {"success": success, "message": "Session extended" if success else "Failed to extend session"}
