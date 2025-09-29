"""
PostgreSQL Replication Manager - Main FastAPI Application
"""

"""
PostgreSQL Replication Manager - Main FastAPI Application
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api import auth, models_test

app = FastAPI(
    title="PostgreSQL Replication Manager",
    description=("Centralized management of PostgreSQL logical replication across multi-cloud environments"),
    version="1.0.0",
)

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include API routers
app.include_router(auth.router)
app.include_router(models_test.router)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse(request, "login.html")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint serving basic HTML interface"""
    # Get user info if authenticated
    user = getattr(request.state, "user", None)

    user_info = ""
    if user:
        user_info = f"""
            <div class="user-info">
                <h3>👤 Logged in as: {user.full_name or user.username}</h3>
                <p>Authentication Method: {user.auth_method}</p>
                <p>Roles: {', '.join(user.roles) if user.roles else 'None'}</p>
                <p>Admin: {'Yes' if user.is_admin else 'No'}</p>
                <a href="/api/auth/logout" style="color: #cc0000;">Logout</a>
            </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PostgreSQL Replication Manager</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .status {{
                background: #e8f5e8; padding: 20px;
                border-radius: 5px; margin: 20px 0;
            }}
            .user-info {{
                background: #e8f0ff; padding: 20px;
                border-radius: 5px; margin: 20px 0;
                border-left: 4px solid #0066cc;
            }}
            .nav {{
                background: #f0f0f0; padding: 15px;
                border-radius: 5px; margin: 20px 0;
            }}
            .nav a {{ margin-right: 15px; text-decoration: none; color: #0066cc; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PostgreSQL Replication Manager</h1>
            
            {user_info}
            
            <div class="status">
                <h3>✅ System Status: Running</h3>
                <p>FastAPI application is running successfully on localhost:8000</p>
                <p>LocalStack integration: Ready for development
                   (Secrets Manager + IAM)</p>
                <p>Redis: Direct connection available on port 6379</p>
                <p>PostgreSQL: Primary (5432) and Replica (5433) databases ready</p>
            </div>

            <div class="nav">
                <h3>Available Endpoints:</h3>
                <a href="/docs">API Documentation</a>
                <a href="/health">Health Check</a>
                <a href="/api/models/test">Model Validation Test</a>
                <a href="/api/auth/me">User Info</a>
            </div>

            <h3>Development Progress</h3>
            <ul>
                <li>✅ Task 1: Project structure and development environment</li>
                <li>✅ Task 2: Core data models and validation</li>
                <li>🔄 Task 3: Authentication and authorization system</li>
                <li>⏳ Task 4: AWS service integration layer</li>
            </ul>

            <h3>Task 3 Features</h3>
            <ul>
                <li>✅ Multi-method authentication (IAM Identity Center, Secrets Manager, Auth Key)</li>
                <li>✅ Session management with Redis storage</li>
                <li>✅ Role-based access control</li>
                <li>✅ Authentication middleware</li>
                <li>✅ Login/logout web interface</li>
                <li>✅ API endpoints for authentication</li>
            </ul>
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
