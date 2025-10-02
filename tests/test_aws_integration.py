"""
AWS integration tests using LocalStack and Docker Compose services.

These tests verify AWS service integrations work correctly with:
- LocalStack for Secrets Manager
- Direct Redis connection (not ElastiCache)
- Direct PostgreSQL connections (not RDS)
"""

import os

import pytest

from app.services.aws_elasticache import ElastiCacheError, ElastiCacheManager
from app.services.aws_rds import RDSClient, RDSError
from app.services.aws_secrets import SecretsManagerClient, SecretsManagerError


class TestSecretsManagerIntegration:
    """Test Secrets Manager integration with LocalStack."""

    @pytest.fixture
    def secrets_client(self):
        """Create Secrets Manager client for LocalStack."""
        return SecretsManagerClient(region_name="us-east-1", endpoint_url="http://localhost:4566")

    @pytest.mark.asyncio
    async def test_get_existing_secret(self, secrets_client):
        """Test retrieving an existing secret from LocalStack."""
        try:
            # This secret should be created by localstack-init/setup.sh
            secret_data = await secrets_client.get_secret("test/postgres/primary")

            assert "username" in secret_data
            assert "password" in secret_data
            assert "host" in secret_data
            assert "port" in secret_data
            assert "dbname" in secret_data

            assert secret_data["username"] == "testuser"
            assert secret_data["host"] == "postgres-primary"

        except SecretsManagerError as e:
            # If LocalStack isn't running or secret doesn't exist, skip test
            pytest.skip(f"LocalStack not available or secret not found: {e}")

    @pytest.mark.asyncio
    async def test_get_database_credentials(self, secrets_client):
        """Test retrieving database credentials."""
        try:
            credentials = await secrets_client.get_database_credentials("test/postgres/primary")

            assert credentials["username"] == "testuser"
            assert credentials["password"] == "testpass"
            assert credentials["host"] == "postgres-primary"
            assert credentials["port"] == 5432
            assert credentials["dbname"] == "testdb"

        except SecretsManagerError as e:
            pytest.skip(f"LocalStack not available: {e}")

    @pytest.mark.asyncio
    async def test_get_nonexistent_secret(self, secrets_client):
        """Test handling of nonexistent secrets."""
        with pytest.raises(SecretsManagerError) as exc_info:
            await secrets_client.get_secret("nonexistent/secret")

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_secret_caching(self, secrets_client):
        """Test that secrets are cached properly."""
        try:
            # First call should retrieve from AWS
            secret1 = await secrets_client.get_secret("test/postgres/primary")

            # Second call should use cache
            secret2 = await secrets_client.get_secret("test/postgres/primary")

            assert secret1 == secret2

            # Check cache info
            cache_info = secrets_client.get_cache_info()
            assert cache_info["total_entries"] >= 1
            assert "test/postgres/primary" in cache_info["entries"]

        except SecretsManagerError as e:
            pytest.skip(f"LocalStack not available: {e}")


class TestElastiCacheIntegration:
    """Test ElastiCache (Redis) integration with Docker Compose Redis."""

    @pytest.fixture
    def redis_manager(self):
        """Create Redis manager for Docker Compose Redis."""
        return ElastiCacheManager(host="localhost", port=6379, socket_timeout=2.0, socket_connect_timeout=2.0)

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_manager):
        """Test basic Redis connection."""
        try:
            async with redis_manager:
                is_connected = await redis_manager.ping()
                assert is_connected is True
        except ElastiCacheError as e:
            pytest.skip(f"Redis not available: {e}")

    @pytest.mark.asyncio
    async def test_redis_operations(self, redis_manager):
        """Test basic Redis operations."""
        try:
            async with redis_manager:
                test_key = "test:aws_integration"
                test_value = "test_value_123"

                # Test set operation
                result = await redis_manager.set(test_key, test_value, ex=60)
                assert result is True

                # Test get operation
                retrieved_value = await redis_manager.get(test_key)
                assert retrieved_value == test_value

                # Test exists operation
                exists_count = await redis_manager.exists(test_key)
                assert exists_count == 1

                # Test delete operation
                deleted_count = await redis_manager.delete(test_key)
                assert deleted_count == 1

                # Verify deletion
                retrieved_after_delete = await redis_manager.get(test_key)
                assert retrieved_after_delete is None

        except ElastiCacheError as e:
            pytest.skip(f"Redis not available: {e}")

    @pytest.mark.asyncio
    async def test_redis_info(self, redis_manager):
        """Test Redis info retrieval."""
        try:
            async with redis_manager:
                info = await redis_manager.get_info()

                assert "redis_version" in info
                assert "connected_clients" in info
                assert "used_memory" in info
                assert isinstance(info["connected_clients"], int)

        except ElastiCacheError as e:
            pytest.skip(f"Redis not available: {e}")

    @pytest.mark.asyncio
    async def test_redis_connection_error_handling(self):
        """Test Redis connection error handling."""
        # Use invalid port to trigger connection error
        redis_manager = ElastiCacheManager(
            host="localhost",
            port=9999,  # Invalid port
            socket_connect_timeout=1.0,
        )

        with pytest.raises(ElastiCacheError):
            async with redis_manager:
                await redis_manager.ping()


class TestRDSIntegration:
    """Test RDS integration (mocked since we're using Docker Compose PostgreSQL)."""

    @pytest.fixture
    def rds_client(self):
        """Create RDS client for LocalStack."""
        return RDSClient(region_name="us-east-1", endpoint_url="http://localhost:4566")

    @pytest.mark.asyncio
    async def test_rds_list_instances_empty(self, rds_client):
        """Test listing RDS instances when none exist."""
        try:
            instances = await rds_client.list_db_instances()
            # LocalStack RDS emulation may return empty list
            assert isinstance(instances, list)
        except RDSError as e:
            pytest.skip(f"LocalStack RDS not available: {e}")

    @pytest.mark.asyncio
    async def test_rds_list_clusters_empty(self, rds_client):
        """Test listing RDS clusters when none exist."""
        try:
            clusters = await rds_client.list_db_clusters()
            # LocalStack RDS emulation may return empty list
            assert isinstance(clusters, list)
        except RDSError as e:
            pytest.skip(f"LocalStack RDS not available: {e}")

    @pytest.mark.asyncio
    async def test_rds_discover_topology_empty(self, rds_client):
        """Test discovering replication topology when no RDS instances exist."""
        try:
            topology = await rds_client.discover_replication_topology()

            assert "discovery_time" in topology
            assert "total_instances" in topology
            assert "total_clusters" in topology
            assert "primary_instances" in topology
            assert "read_replicas" in topology
            assert "clusters" in topology
            assert "replication_chains" in topology

            # With Docker Compose setup, these should be empty
            assert topology["total_instances"] == 0
            assert topology["total_clusters"] == 0

        except RDSError as e:
            pytest.skip(f"LocalStack RDS not available: {e}")

    @pytest.mark.asyncio
    async def test_rds_generate_auth_token(self, rds_client):
        """Test generating IAM auth token."""
        try:
            token = await rds_client.generate_auth_token(db_hostname="localhost", port=5432, db_username="testuser")

            # Token should be a non-empty string
            assert isinstance(token, str)
            assert len(token) > 0

        except RDSError as e:
            pytest.skip(f"LocalStack RDS not available: {e}")


class TestAWSIntegrationEndpoints:
    """Test AWS integration API endpoints."""

    # Use the global client fixture from conftest.py

    def test_aws_test_endpoint(self, client):
        """Test the main AWS integration test endpoint."""
        # Set environment variables for testing
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6379"

        response = client.get("/api/aws/test")

        # Should return 200 even if services are not available
        assert response.status_code == 200

        data = response.json()
        assert "secrets_manager" in data
        assert "elasticache" in data
        assert "rds" in data
        assert "overall_status" in data

        # Each service should have required fields
        for service_name in ["secrets_manager", "elasticache", "rds"]:
            service_data = data[service_name]
            assert "service" in service_data
            assert "status" in service_data
            assert "message" in service_data
            assert service_data["service"] == service_name

    def test_secrets_test_endpoint(self, client):
        """Test the Secrets Manager test endpoint."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"

        response = client.get("/api/aws/secrets/test")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "secrets_manager"
        assert "status" in data
        assert "message" in data

    def test_elasticache_test_endpoint(self, client):
        """Test the ElastiCache test endpoint."""
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6379"

        response = client.get("/api/aws/elasticache/test")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "elasticache"
        assert "status" in data
        assert "message" in data

    def test_rds_test_endpoint(self, client):
        """Test the RDS test endpoint."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"

        response = client.get("/api/aws/rds/test")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "rds"
        assert "status" in data
        assert "message" in data

    def test_get_secret_endpoint(self, client):
        """Test the get secret endpoint."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"

        # Test with existing secret
        response = client.get("/api/aws/secrets/test/postgres/primary")

        # May return 400 if LocalStack not running, which is fine for testing
        assert response.status_code in [200, 400]

        if response.status_code == 200:
            data = response.json()
            assert "secret_name" in data
            assert "data" in data
            assert data["secret_name"] == "test/postgres/primary"

    def test_rds_instances_endpoint(self, client):
        """Test the RDS instances endpoint."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"

        response = client.get("/api/aws/rds/instances")

        # May return 400 if LocalStack not running
        assert response.status_code in [200, 400]

        if response.status_code == 200:
            data = response.json()
            assert "total_instances" in data
            assert "instances" in data
            assert isinstance(data["instances"], list)

    def test_rds_topology_endpoint(self, client):
        """Test the RDS topology endpoint."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"

        response = client.get("/api/aws/rds/topology")

        # May return 400 if LocalStack not running
        assert response.status_code in [200, 400]

        if response.status_code == 200:
            data = response.json()
            assert "discovery_time" in data
            assert "total_instances" in data
            assert "primary_instances" in data
            assert "read_replicas" in data
