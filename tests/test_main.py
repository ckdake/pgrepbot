"""
Basic tests for the main FastAPI application
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test the root endpoint returns HTML"""
    response = client.get("/")
    assert response.status_code == 200
    assert "PostgreSQL Replication Manager" in response.text
    assert "text/html" in response.headers["content-type"]


def test_health_check():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "postgres-replication-manager"
    assert "version" in data
