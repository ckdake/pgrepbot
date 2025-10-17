"""
Test configuration and fixtures.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.api import alerts, auth, aws, database_config, databases, migrations, models_test, replication


@pytest.fixture
def test_app():
    """Create a test FastAPI app without authentication middleware."""
    app = FastAPI(
        title="PostgreSQL Replication Manager - Test",
        description="Test version without authentication middleware",
        version="1.0.0",
    )

    # Static files
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Templates (not used in tests but needed for import compatibility)
    # templates = Jinja2Templates(directory="app/templates")

    # Include API routers (without authentication middleware)
    app.include_router(auth.router)
    app.include_router(models_test.router)
    app.include_router(aws.router)
    app.include_router(databases.router)
    app.include_router(database_config.router)
    app.include_router(migrations.router)
    app.include_router(replication.router)
    app.include_router(alerts.router)

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Root endpoint that returns HTML"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>PostgreSQL Replication Manager</title>
        </head>
        <body>
            <h1>PostgreSQL Replication Manager</h1>
            <p>Test version</p>
        </body>
        </html>
        """

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        """Login page for testing"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>PostgreSQL Replication Manager - Login</title>
        </head>
        <body>
            <div class="login-container">
                <h1>PostgreSQL Replication Manager</h1>
                <h2>Sign in with AWS IAM Identity Center</h2>
                <form>
                    <label>Username</label>
                    <input type="text" name="username">
                    <label>Authentication Key</label>
                    <input type="password" name="auth_key">
                    <button type="submit">Login</button>
                </form>
            </div>
        </body>
        </html>
        """

    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancer integration"""
        return {
            "status": "healthy",
            "service": "postgres-replication-manager",
            "version": "1.0.0",
        }

    return app


@pytest.fixture
def client(test_app):
    """Test client for FastAPI app without authentication."""
    return TestClient(test_app)
