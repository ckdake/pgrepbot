"""
Tests for migration execution service.
"""

from unittest.mock import AsyncMock

import pytest

from app.models.database import DatabaseConfig
from app.services.migration_executor import MigrationExecutor
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService


@pytest.fixture
def mock_connection_manager():
    """Mock PostgreSQL connection manager"""
    return AsyncMock(spec=PostgreSQLConnectionManager)


@pytest.fixture
def mock_discovery_service():
    """Mock replication discovery service"""
    return AsyncMock(spec=ReplicationDiscoveryService)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.set = AsyncMock()
    mock_client.get = AsyncMock()
    mock_client.scan = AsyncMock(return_value=(0, []))
    return mock_client


@pytest.fixture
def migration_executor(mock_connection_manager, mock_discovery_service, mock_redis):
    """Migration executor with mocked dependencies"""
    return MigrationExecutor(
        connection_manager=mock_connection_manager, discovery_service=mock_discovery_service, redis_client=mock_redis
    )


@pytest.fixture
def sample_database_config():
    """Sample database configuration"""
    return DatabaseConfig(
        name="test-primary",
        host="localhost",
        port=5432,
        database="testdb",
        role="primary",
        credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
        use_iam_auth=False,
        cloud_provider="aws",
        region="us-east-1",
        environment="test",
    )


class TestMigrationExecutor:
    """Test migration executor functionality"""

    def test_init(self, mock_connection_manager, mock_discovery_service, mock_redis):
        """Test migration executor initialization"""
        executor = MigrationExecutor(
            connection_manager=mock_connection_manager,
            discovery_service=mock_discovery_service,
            redis_client=mock_redis,
        )
        assert executor.connection_manager == mock_connection_manager
        assert executor.discovery_service == mock_discovery_service
        assert executor.redis_client == mock_redis

    @pytest.mark.asyncio
    async def test_create_migration_tables(self, migration_executor, sample_database_config):
        """Test creating migration tables"""
        databases = [sample_database_config]

        # Mock successful table creation
        migration_executor.connection_manager.execute_query.return_value = None

        results = await migration_executor.create_migration_tables(databases)

        assert len(results) == 1
        assert results[sample_database_config.id] is True
        migration_executor.connection_manager.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_migration(self, migration_executor):
        """Test storing a migration"""
        filename = "001_create_users.sql"
        content = "CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(100));"
        created_by = "test_user"

        migration_id = await migration_executor.store_migration(filename, content, created_by)

        assert migration_id is not None
        assert filename in migration_id
        migration_executor.redis_client.set.assert_called()

    @pytest.mark.asyncio
    async def test_store_migration_invalid_filename(self, migration_executor):
        """Test storing migration with invalid filename"""
        filename = "invalid_file.txt"  # Not .sql
        content = "CREATE TABLE test (id INT);"
        created_by = "test_user"

        with pytest.raises(ValueError, match="must end with .sql"):
            await migration_executor.store_migration(filename, content, created_by)

    @pytest.mark.asyncio
    async def test_get_migration_table_name(self, migration_executor):
        """Test migration table name generation"""
        # This tests the private method indirectly through create_migration_tables
        databases = [
            DatabaseConfig(
                name="test-db",
                host="localhost",
                port=5432,
                database="testdb",
                role="primary",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
                use_iam_auth=False,
                cloud_provider="aws",
                region="us-east-1",
                environment="test",
            )
        ]

        migration_executor.connection_manager.execute_query.return_value = None

        results = await migration_executor.create_migration_tables(databases)

        # Should succeed in creating table
        assert len(results) == 1
        assert list(results.values())[0] is True
