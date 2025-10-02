"""
Tests for replication stream management service.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import DatabaseConfig
from app.services.replication_management import (
    ReplicationManagementError,
    ReplicationStreamManager,
)


@pytest.fixture
def mock_connection_manager():
    """Mock PostgreSQL connection manager."""
    manager = MagicMock()

    # Mock health status (synchronous method)
    mock_health = MagicMock()
    mock_health.is_healthy = True
    mock_health.error_message = None
    manager.get_health_status.return_value = mock_health

    # Mock query execution (async method)
    manager.execute_query = AsyncMock()

    return manager


@pytest.fixture
def stream_manager(mock_connection_manager):
    """Create a replication stream manager with mocked dependencies."""
    return ReplicationStreamManager(mock_connection_manager)


@pytest.fixture
def sample_databases():
    """Sample database configurations."""
    return [
        DatabaseConfig(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="Primary Database",
            host="postgres-primary",
            port=5432,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:primary-creds",
            role="primary",
            environment="test",
            cloud_provider="aws",
        ),
        DatabaseConfig(
            id="550e8400-e29b-41d4-a716-446655440001",
            name="Replica Database",
            host="postgres-replica",
            port=5433,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:replica-creds",
            role="replica",
            environment="test",
            cloud_provider="aws",
        ),
    ]


class TestReplicationStreamManager:
    """Test cases for ReplicationStreamManager."""

    @pytest.mark.asyncio
    async def test_create_logical_replication_stream_success(self, stream_manager, sample_databases):
        """Test successful logical replication stream creation."""
        # Mock successful query execution
        stream_manager.connection_manager.execute_query.return_value = []

        # Mock replication permissions check
        stream_manager.connection_manager.execute_query.side_effect = [
            [{"rolreplication": True}],  # Permissions check
            [],  # CREATE PUBLICATION
            [],  # CREATE SUBSCRIPTION
        ]

        # Create stream
        stream = await stream_manager.create_logical_replication_stream(
            source_db_id=sample_databases[0].id,
            target_db_id=sample_databases[1].id,
            publication_name="test_pub",
            subscription_name="test_sub",
            table_names=["users", "orders"],
            initial_sync=True,
        )

        # Verify stream properties
        assert stream.type == "logical"
        assert stream.source_db_id == sample_databases[0].id
        assert stream.target_db_id == sample_databases[1].id
        assert stream.publication_name == "test_pub"
        assert stream.subscription_name == "test_sub"
        assert stream.status == "active"
        assert stream.is_managed is True
        assert stream.id is not None

        # Verify queries were called
        assert stream_manager.connection_manager.execute_query.call_count >= 2

    @pytest.mark.asyncio
    async def test_create_logical_replication_stream_all_tables(self, stream_manager, sample_databases):
        """Test creating replication stream for all tables."""
        # Mock successful execution
        stream_manager.connection_manager.execute_query.side_effect = [
            [{"rolreplication": True}],  # Permissions check
            [],  # CREATE PUBLICATION FOR ALL TABLES
            [],  # CREATE SUBSCRIPTION
        ]

        stream = await stream_manager.create_logical_replication_stream(
            source_db_id=sample_databases[0].id,
            target_db_id=sample_databases[1].id,
            publication_name="test_pub_all",
            subscription_name="test_sub_all",
            table_names=None,  # All tables
            initial_sync=False,
        )

        assert stream.publication_name == "test_pub_all"
        assert stream.subscription_name == "test_sub_all"

    @pytest.mark.asyncio
    async def test_create_logical_replication_stream_database_not_accessible(self, stream_manager, sample_databases):
        """Test stream creation with inaccessible database."""
        # Mock unhealthy database
        mock_health = MagicMock()
        mock_health.is_healthy = False
        mock_health.error_message = "Connection failed"
        stream_manager.connection_manager.get_health_status.return_value = mock_health

        with pytest.raises(ReplicationManagementError) as exc_info:
            await stream_manager.create_logical_replication_stream(
                source_db_id=sample_databases[0].id,
                target_db_id=sample_databases[1].id,
                publication_name="test_pub",
                subscription_name="test_sub",
            )

        assert "not accessible" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_destroy_logical_replication_stream_success(self, stream_manager, sample_databases):
        """Test successful logical replication stream destruction."""
        # Mock successful query execution
        stream_manager.connection_manager.execute_query.return_value = []

        # Should not raise any exception
        await stream_manager.destroy_logical_replication_stream(
            source_db_id=sample_databases[0].id,
            target_db_id=sample_databases[1].id,
            publication_name="test_pub",
            subscription_name="test_sub",
        )

        # Verify both DROP queries were called
        assert stream_manager.connection_manager.execute_query.call_count == 2

    @pytest.mark.asyncio
    async def test_validate_replication_stream_success(self, stream_manager, sample_databases):
        """Test successful replication stream validation."""
        # Mock successful validation responses
        stream_manager.connection_manager.execute_query.side_effect = [
            [{"rolreplication": True}],  # Replication permissions
            [{"table_name": "users"}, {"table_name": "orders"}],  # Table existence
        ]

        result = await stream_manager.validate_replication_stream(
            source_db_id=sample_databases[0].id,
            target_db_id=sample_databases[1].id,
            table_names=["users", "orders"],
        )

        assert result["success"] is True
        assert result["source_db_accessible"] is True
        assert result["target_db_accessible"] is True
        assert result["replication_user_exists"] is True
        assert len(result["issues"]) == 0

    @pytest.mark.asyncio
    async def test_validate_replication_stream_missing_tables(self, stream_manager, sample_databases):
        """Test validation with missing tables."""
        # Mock responses
        stream_manager.connection_manager.execute_query.side_effect = [
            [{"rolreplication": True}],  # Replication permissions
            [{"table_name": "users"}],  # Only one table exists
        ]

        result = await stream_manager.validate_replication_stream(
            source_db_id=sample_databases[0].id,
            target_db_id=sample_databases[1].id,
            table_names=["users", "orders", "products"],
        )

        assert result["success"] is False
        assert len(result["issues"]) > 0
        assert "Missing tables" in result["issues"][0]

    @pytest.mark.asyncio
    async def test_validate_replication_stream_no_permissions(self, stream_manager, sample_databases):
        """Test validation with insufficient permissions."""
        # Mock no replication permissions
        stream_manager.connection_manager.execute_query.side_effect = [
            [{"rolreplication": False}],  # No replication permissions
        ]

        result = await stream_manager.validate_replication_stream(
            source_db_id=sample_databases[0].id,
            target_db_id=sample_databases[1].id,
        )

        assert result["success"] is False
        assert result["replication_user_exists"] is False
        assert any("replication privileges" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_check_table_existence(self, stream_manager, sample_databases):
        """Test table existence checking."""
        # Mock table query response
        stream_manager.connection_manager.execute_query.return_value = [
            {"table_name": "users"},
            {"table_name": "orders"},
        ]

        missing_tables = await stream_manager._check_table_existence(
            sample_databases[0].id, ["users", "orders", "products"]
        )

        assert missing_tables == ["products"]

    @pytest.mark.asyncio
    async def test_check_table_existence_empty_list(self, stream_manager, sample_databases):
        """Test table existence checking with empty list."""
        missing_tables = await stream_manager._check_table_existence(sample_databases[0].id, [])

        assert missing_tables == []

    @pytest.mark.asyncio
    async def test_create_publication_specific_tables(self, stream_manager, sample_databases):
        """Test creating publication for specific tables."""
        stream_manager.connection_manager.execute_query.return_value = []

        await stream_manager._create_publication(sample_databases[0].id, "test_pub", ["users", "orders"])

        # Verify the correct SQL was executed
        call_args = stream_manager.connection_manager.execute_query.call_args
        assert "CREATE PUBLICATION test_pub FOR TABLE users, orders" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_create_publication_all_tables(self, stream_manager, sample_databases):
        """Test creating publication for all tables."""
        stream_manager.connection_manager.execute_query.return_value = []

        await stream_manager._create_publication(sample_databases[0].id, "test_pub_all", None)

        # Verify the correct SQL was executed
        call_args = stream_manager.connection_manager.execute_query.call_args
        assert "CREATE PUBLICATION test_pub_all FOR ALL TABLES" in call_args[0][1]
