"""
PostgreSQL Replication Manager - Main FastAPI Application
"""

import os

import redis.asyncio as redis
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import alerts, auth, aws, database_config, databases, migrations, models_test, replication
from app.middleware.auth import AuthenticationMiddleware, get_current_user_optional
from app.models.auth import User
from app.services.background_tasks import start_background_tasks, stop_background_tasks

app = FastAPI(
    title="PostgreSQL Replication Manager",
    description=("Centralized management of PostgreSQL logical replication across multi-cloud environments"),
    version="1.0.0",
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Add authentication middleware

redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
app.add_middleware(AuthenticationMiddleware, redis_client=redis_client)

# Include API routers
app.include_router(auth.router)
app.include_router(models_test.router)
app.include_router(aws.router)
app.include_router(databases.router)
app.include_router(database_config.router)
app.include_router(migrations.router)
app.include_router(replication.router)
app.include_router(alerts.router)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: User | None = Depends(get_current_user_optional)):
    """Root endpoint serving the main web interface"""
    if not user:
        # Redirect to login if not authenticated
        return templates.TemplateResponse("login.html", {"request": request})

    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    """Dashboard page"""
    if not user:
        return templates.TemplateResponse("login.html", {"request": request})

    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancer integration"""
    return {
        "status": "healthy",
        "service": "postgres-replication-manager",
        "version": "1.0.0",
    }


@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    try:
        await start_background_tasks(redis_client)
    except Exception as e:
        # Log error but don't fail startup
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to start background tasks: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    try:
        await stop_background_tasks()
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to stop background tasks: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
