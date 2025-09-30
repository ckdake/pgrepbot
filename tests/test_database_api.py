"""
Tests for database API endpoints.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestDatabaseAPI:
    """Test database API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up environment variables for testing."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"
        os.environ["AWS_ACCESS_KEY_ID"] = "test"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6379"

    def test_database_test_endpoint_structure(self, client):
        """Test that the database test endpoint returns proper structure."""
        response = client.get("/api/databases/test")

        # Should return 200 even if services are not available
        assert response.status_code == 200

        data = response.json()
        assert "total_databases" in data
        assert "healthy_databases" in data
        assert "databases" in data
        assert "pool_stats" in data
        assert "overall_status" in data

        # Check that databases is a list
        assert isinstance(data["databases"], list)

        # Check that pool_stats is a dict
        assert isinstance(data["pool_stats"], dict)

        # Overall status should be one of the expected values
        assert data["overall_status"] in ["healthy", "degraded", "unhealthy"]

    def test_database_health_endpoint(self, client):
        """Test the database health endpoint."""
        response = client.get("/api/databases/health")

        # Should return 200 even if services are not available
        assert response.status_code == 200

        data = response.json()
        assert "databases" in data
        assert isinstance(data["databases"], dict)

    def test_database_pools_endpoint(self, client):
        """Test the database pools endpoint."""
        response = client.get("/api/databases/pools")

        # Should return 200 even if services are not available
        assert response.status_code == 200

        data = response.json()
        assert "pools" in data
        assert "total_pools" in data
        assert isinstance(data["pools"], dict)
        assert isinstance(data["total_pools"], int)

    def test_credentials_test_endpoint(self, client):
        """Test the credentials test endpoint."""
        response = client.get("/api/databases/credentials/test")

        # Should return 200 even if services are not available
        assert response.status_code == 200

        data = response.json()
        assert "primary_database" in data
        assert "replica_database" in data

        # Check structure of database credential test results
        for db_key in ["primary_database", "replica_database"]:
            db_data = data[db_key]
            assert "secret_name" in db_data
            assert "status" in db_data
            assert db_data["status"] in ["success", "failed"]

    def test_query_endpoint_security(self, client):
        """Test that the query endpoint only allows SELECT queries."""
        # Test with non-SELECT query
        response = client.post("/api/databases/query/test_db", params={"query": "DROP TABLE test"})
        assert response.status_code == 400
        assert "Only SELECT queries are allowed" in response.json()["detail"]

        # Test with INSERT query
        response = client.post("/api/databases/query/test_db", params={"query": "INSERT INTO test VALUES (1)"})
        assert response.status_code == 400
        assert "Only SELECT queries are allowed" in response.json()["detail"]

        # Test with UPDATE query
        response = client.post("/api/databases/query/test_db", params={"query": "UPDATE test SET id=1"})
        assert response.status_code == 400
        assert "Only SELECT queries are allowed" in response.json()["detail"]

        # Test with DELETE query
        response = client.post("/api/databases/query/test_db", params={"query": "DELETE FROM test"})
        assert response.status_code == 400
        assert "Only SELECT queries are allowed" in response.json()["detail"]

    def test_query_endpoint_allows_select(self, client):
        """Test that the query endpoint allows SELECT queries."""
        # This will fail because the database doesn't exist, but it should pass the security check
        response = client.post("/api/databases/query/test_db", params={"query": "SELECT 1"})

        # Should not be a 400 security error, but may be 400 for other reasons (database not found)
        # or 500 for internal errors
        assert response.status_code in [400, 500]

        # If it's a 400, it should not be about query security
        if response.status_code == 400:
            detail = response.json()["detail"]
            assert "Only SELECT queries are allowed" not in detail

    def test_single_database_test_endpoint(self, client):
        """Test the single database test endpoint."""
        # Test with a non-existent database
        response = client.get("/api/databases/test/nonexistent_db")

        # Should return 200 with unhealthy status for non-existent database
        assert response.status_code == 200

        data = response.json()
        assert "database_id" in data
        assert "status" in data
        assert data["database_id"] == "nonexistent_db"
        assert data["status"] == "unhealthy"


class TestDatabaseModels:
    """Test database API response models."""

    def test_database_test_response_model(self):
        """Test DatabaseTestResponse model."""
        from app.api.databases import DatabaseTestResponse

        response = DatabaseTestResponse(
            database_id="test_db", status="healthy", message="Test message", data={"key": "value"}, error=""
        )

        assert response.database_id == "test_db"
        assert response.status == "healthy"
        assert response.message == "Test message"
        assert response.data == {"key": "value"}
        assert response.error == ""

    def test_database_health_response_model(self):
        """Test DatabaseHealthResponse model."""
        from app.api.databases import DatabaseHealthResponse

        response = DatabaseHealthResponse(
            database_id="test_db",
            is_healthy=True,
            last_check="2023-01-01T00:00:00",
            error_message=None,
            response_time_ms=50.0,
            server_version="15.14",
        )

        assert response.database_id == "test_db"
        assert response.is_healthy is True
        assert response.last_check == "2023-01-01T00:00:00"
        assert response.error_message is None
        assert response.response_time_ms == 50.0
        assert response.server_version == "15.14"

    def test_database_connection_status_model(self):
        """Test DatabaseConnectionStatus model."""
        from app.api.databases import DatabaseConnectionStatus, DatabaseHealthResponse

        health_response = DatabaseHealthResponse(
            database_id="test_db", is_healthy=True, last_check="2023-01-01T00:00:00"
        )

        status = DatabaseConnectionStatus(
            total_databases=1,
            healthy_databases=1,
            databases=[health_response],
            pool_stats={"test_db": {"size": 1, "max_size": 5}},
            overall_status="healthy",
        )

        assert status.total_databases == 1
        assert status.healthy_databases == 1
        assert len(status.databases) == 1
        assert status.databases[0].database_id == "test_db"
        assert status.pool_stats == {"test_db": {"size": 1, "max_size": 5}}
        assert status.overall_status == "healthy"


class TestConnectionManagerMocking:
    """Test connection manager with proper mocking."""

    @pytest.mark.asyncio
    async def test_connection_manager_initialization(self):
        """Test that connection manager can be initialized."""
        from app.services.postgres_connection import PostgreSQLConnectionManager

        manager = PostgreSQLConnectionManager(
            secrets_client=None, rds_client=None, pool_min_size=1, pool_max_size=2, health_check_interval=30
        )

        assert manager.pool_min_size == 1
        assert manager.pool_max_size == 2
        assert manager.health_check_interval == 30
        assert len(manager._pools) == 0
        assert len(manager._credentials) == 0
        assert len(manager._health_status) == 0

    @pytest.mark.asyncio
    async def test_connection_manager_context_manager(self):
        """Test connection manager as context manager."""
        from app.services.postgres_connection import PostgreSQLConnectionManager

        async with PostgreSQLConnectionManager() as manager:
            assert manager is not None
            assert len(manager._pools) == 0

    def test_health_status_for_nonexistent_database(self):
        """Test getting health status for non-existent database."""
        from app.services.postgres_connection import PostgreSQLConnectionManager

        manager = PostgreSQLConnectionManager()
        health = manager.get_health_status("nonexistent")

        assert health.is_healthy is False
        assert health.error_message == "Database not found"

    def test_pool_stats_empty(self):
        """Test getting pool stats when no pools exist."""
        from app.services.postgres_connection import PostgreSQLConnectionManager

        manager = PostgreSQLConnectionManager()
        stats = manager.get_pool_stats()

        assert stats == {}

    def test_pool_stats_for_nonexistent_database(self):
        """Test getting pool stats for non-existent database."""
        from app.services.postgres_connection import PostgreSQLConnectionManager

        manager = PostgreSQLConnectionManager()
        stats = manager.get_pool_stats("nonexistent")

        assert stats == {}
