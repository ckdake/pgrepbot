"""
PostgreSQL Replication Manager - Main FastAPI Application
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.models_test import router as models_router

app = FastAPI(
    title="PostgreSQL Replication Manager",
    description=("Centralized management of PostgreSQL logical replication across multi-cloud environments"),
    version="1.0.0",
)

# Include API routers
app.include_router(models_router)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint serving basic HTML interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>PostgreSQL Replication Manager</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .status {
                background: #e8f5e8; padding: 20px;
                border-radius: 5px; margin: 20px 0;
            }
            .nav {
                background: #f0f0f0; padding: 15px;
                border-radius: 5px; margin: 20px 0;
            }
            .nav a { margin-right: 15px; text-decoration: none; color: #0066cc; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PostgreSQL Replication Manager</h1>
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
            </div>

            <h3>Development Progress</h3>
            <ul>
                <li>✅ Task 1: Project structure and development environment</li>
                <li>🔄 Task 2: Core data models and validation</li>
                <li>⏳ Task 3: Authentication and authorization system</li>
                <li>⏳ Task 4: AWS service integration layer</li>
            </ul>

            <h3>Task 2 Features</h3>
            <ul>
                <li>✅ Pydantic data models
                    (DatabaseConfig, ReplicationStream, MigrationExecution)</li>
                <li>✅ Redis serialization utilities</li>
                <li>✅ Comprehensive model validation</li>
                <li>✅ API endpoints for testing models</li>
                <li>✅ Unit tests for all models</li>
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
