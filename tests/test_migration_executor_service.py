"""
Tests for the migration executor service
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.database import DatabaseConfig
from app.services.migration_executor import MigrationExecutionResult, MigrationExecutor, MigrationRecord
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService


class TestMigrationRecord:
    """Test the MigrationRecord class"""

    def test_migration_record_creation(self):
        """Test creating a migration record"""
        created_at = datetime.now(UTC)
        record = MigrationRecord(
            migration_id="123_test_migration.sql",
            filename="test_migration.sql",
            content="CREATE TABLE test (id INTEGER);",
            created_at=created_at,
            created_by="test_user",
        )

        assert record.migration_id == "123_test_migration.sql"
        assert record.filename == "test_migration.sql"
        assert record.content == "CREATE TABLE test (id INTEGER);"
        assert record.created_at == created_at
        assert record.created_by == "test_user"
        assert record.status == "pending"
        assert record.execution_log == []
        assert record.retry_count == 0

    def test_migration_record_with_custom_status(self):
        """Test creating a migration record with custom status"""
        record = MigrationRecord(
            migration_id="123_test_migration.sql",
            filename="test_migration.sql",
            content="CREATE TABLE test (id INTEGER);",
            created_at=datetime.now(UTC),
            created_by="test_user",
            status="running",
        )

        assert record.status == "running"


class TestMigrationExecutionResult:
    """Test the MigrationExecutionResult class"""

    def test_successful_result(self):
        """Test creating a successful migration result"""
        result = MigrationExecutionResult(
            database_id="db1",
            database_name="Test DB",
            success=True,
            execution_time=1.5,
            rows_affected=10,
        )

        assert result.database_id == "db1"
        assert result.database_name == "Test DB"
        assert result.success is True
        assert result.execution_time == 1.5
        assert result.error_message is None
        assert result.rows_affected == 10

    def test_failed_result(self):
        """Test creating a failed migration result"""
        result = MigrationExecutionResult(
            database_id="db1",
            database_name="Test DB",
            success=False,
            execution_time=0.5,
            error_message="Syntax error",
        )

        assert result.database_id == "db1"
        assert result.database_name == "Test DB"
        assert result.success is False
        assert result.execution_time == 0.5
        assert result.error_message == "Syntax error"
        assert result.rows_affected is None


class TestMigrationExecutor:
    """Test the MigrationExecutor class"""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock PostgreSQL connection manager"""
        return AsyncMock(spec=PostgreSQLConnectionManager)

    @pytest.fixture
    def mock_discovery_service(self):
        """Mock replication discovery service"""
        return AsyncMock(spec=ReplicationDiscoveryService)

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client"""
        return AsyncMock()

    @pytest.fixture
    def migration_executor(self, mock_connection_manager, mock_discovery_service, mock_redis_client):
        """Create MigrationExecutor instance with mocked dependencies"""
        return MigrationExecutor(
            connection_manager=mock_connection_manager,
            discovery_service=mock_discovery_service,
            redis_client=mock_redis_client,
        )

    def test_init(self, migration_executor, mock_connection_manager, mock_discovery_service, mock_redis_client):
        """Test MigrationExecutor initialization"""
        assert migration_executor.connection_manager == mock_connection_manager
        assert migration_executor.discovery_service == mock_discovery_service
        assert migration_executor.redis_client == mock_redis_client

    async def test_create_migration_tables_success(self, migration_executor, mock_connection_manager):
        """Test successful creation of migration tables"""
        # Mock database configs
        db_configs = [
            DatabaseConfig(
                id="db1",
                name="Primary DB",
                host="localhost",
                port=5432,
                database="primary",
                role="primary",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:db1-credentials",
                environment="test",
                cloud_provider="aws",
            ),
            DatabaseConfig(
                id="db2",
                name="Replica DB",
                host="localhost",
                port=5433,
                database="replica",
                role="replica",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:db2-credentials",
                environment="test",
                cloud_provider="aws",
            ),
        ]

        # Mock successful query execution
        mock_connection_manager.execute_query.return_value = None

        # Mock _get_migration_table_name
        migration_executor._get_migration_table_name = AsyncMock(side_effect=["migrations_primary", "migrations_replica"])

        results = await migration_executor.create_migration_tables(db_configs)

        assert results["db1"] is True
        assert results["db2"] is True
        assert mock_connection_manager.execute_query.call_count == 2

    async def test_create_migration_tables_failure(self, migration_executor, mock_connection_manager):
        """Test migration table creation with database failure"""
        # Mock database configs
        db_configs = [
            DatabaseConfig(
                id="db1",
                name="Primary DB",
                host="localhost",
                port=5432,
                database="primary",
                role="primary",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:db1-credentials",
                environment="test",
                cloud_provider="aws",
            ),
        ]

        # Mock query execution failure
        mock_connection_manager.execute_query.side_effect = Exception("Database error")

        # Mock _get_migration_table_name
        migration_executor._get_migration_table_name = AsyncMock(return_value="migrations_primary")

        results = await migration_executor.create_migration_tables(db_configs)

        assert results["db1"] is False

    async def test_store_migration_success(self, migration_executor, mock_redis_client):
        """Test successful migration storage"""
        filename = "001_create_users.sql"
        content = "CREATE TABLE users (id INTEGER PRIMARY KEY);"
        created_by = "test_user"

        # Mock time.time() to get predictable migration ID
        with patch("app.services.migration_executor.time.time", return_value=1234567890):
            with patch.object(MigrationRecord, 'save_to_redis', new_callable=AsyncMock) as mock_save:
                migration_id = await migration_executor.store_migration(filename, content, created_by)

        expected_id = "1234567890_001_create_users.sql"
        assert migration_id == expected_id

        # Verify Redis operations
        mock_redis_client.sadd.assert_called_once_with("pending_migrations", expected_id)
        mock_save.assert_called_once()

    async def test_store_migration_invalid_filename(self, migration_executor):
        """Test storing migration with invalid filename"""
        filename = "invalid_migration.txt"  # Not .sql
        content = "CREATE TABLE test (id INTEGER);"
        created_by = "test_user"

        with pytest.raises(ValueError, match="Migration filename must end with .sql"):
            await migration_executor.store_migration(filename, content, created_by)


class TestMigrationExecutorIntegration:
    """Integration tests for MigrationExecutor"""

    @pytest.fixture
    async def redis_client(self):
        """Real Redis client for integration tests"""
        import redis.asyncio as redis
        client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)
        yield client
        # Cleanup
        await client.flushdb()
        await client.aclose()

    @pytest.fixture
    def migration_executor_real_redis(self, redis_client):
        """MigrationExecutor with real Redis client"""
        mock_connection_manager = AsyncMock(spec=PostgreSQLConnectionManager)
        mock_discovery_service = AsyncMock(spec=ReplicationDiscoveryService)

        return MigrationExecutor(
            connection_manager=mock_connection_manager,
            discovery_service=mock_discovery_service,
            redis_client=redis_client,
        )

    async def test_store_and_retrieve_migration_integration(self, migration_executor_real_redis):
        """Test storing and retrieving migration with real Redis"""
        filename = "001_create_users.sql"
        content = "CREATE TABLE users (id INTEGER PRIMARY KEY);"
        created_by = "test_user"

        # Store migration
        migration_id = await migration_executor_real_redis.store_migration(filename, content, created_by)

        # Verify migration was stored
        migration_data = await migration_executor_real_redis.redis_client.get(f"migration:{migration_id}")
        assert migration_data is not None

        # Verify migration was added to pending list
        pending_migrations = await migration_executor_real_redis.redis_client.smembers("pending_migrations")
        assert migration_id in pending_migrations
