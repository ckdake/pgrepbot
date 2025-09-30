"""
Tests for replication discovery and monitoring service.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.database import DatabaseConfig
from app.models.replication import ReplicationStream, ReplicationMetrics
from app.services.replication_discovery import (
    ReplicationDiscoveryService,
    ReplicationDiscoveryError,
    LogicalReplicationInfo,
    PhysicalReplicationInfo,
)


@pytest.fixture
def mock_connection_manager():
    """Mock PostgreSQL connection manager."""
    manager = AsyncMock()
    return manager


@pytest.fixture
def mock_rds_client():
    """Mock RDS client."""
    client = AsyncMock()
    return client


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
            port=5432,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:replica-creds",
            role="replica",
            environment="test",
            cloud_provider="aws",
        ),
    ]


@pytest.fixture
def discovery_service(mock_connection_manager, mock_rds_client):
    """Replication discovery service instance."""
    return ReplicationDiscoveryService(
        connection_manager=mock_connection_manager,
        rds_client=mock_rds_client,
    )


class TestReplicationDiscoveryService:
    """Test cases for ReplicationDiscoveryService."""

    @pytest.mark.asyncio
    async def test_discover_logical_replication_success(
        self, discovery_service, sample_databases, mock_connection_manager
    ):
        """Test successful logical replication discovery."""
        # Mock publication discovery
        publication_results = [
            {
                "pubname": "test_publication",
                "puballtables": True,
                "pubinsert": True,
                "pubupdate": True,
                "pubdelete": True,
                "pubtruncate": True,
                "tables": [],
            }
        ]

        # Mock subscription discovery
        subscription_results = [
            {
                "subname": "test_subscription",
                "subenabled": True,
                "subconninfo": "host=postgres-primary port=5432 dbname=testdb user=testuser",
                "subslotname": "test_subscription",
                "subsynccommit": "off",
                "subpublications": ["test_publication"],
                "received_lsn": "0/1234ABCD",
                "last_msg_send_time": datetime.utcnow(),
                "last_msg_receipt_time": datetime.utcnow(),
                "latest_end_lsn": "0/1234ABCD",
                "latest_end_time": datetime.utcnow(),
            }
        ]

        # Mock table count
        table_count_results = [{"table_count": 5}]

        # Mock connection manager methods
        from app.services.postgres_connection import ConnectionHealth
        mock_health = ConnectionHealth(
            is_healthy=False,
            last_check=datetime.utcnow(),
            error_message="Not connected"
        )
        mock_connection_manager.get_health_status.return_value = mock_health
        mock_connection_manager.add_database = AsyncMock()
        
        # Configure mock responses - need to handle multiple calls
        def mock_execute_query(db_id, query, *args):
            if "pg_publication" in query:
                return publication_results
            elif "COUNT(*)" in query and "information_schema.tables" in query:
                return table_count_results
            elif "pg_subscription" in query:
                return subscription_results
            else:
                return []
        
        mock_connection_manager.execute_query.side_effect = mock_execute_query

        # Execute discovery
        streams = await discovery_service.discover_logical_replication(sample_databases)

        # Verify results
        assert len(streams) == 1
        stream = streams[0]
        assert stream.type == "logical"
        assert stream.publication_name == "test_publication"
        assert stream.subscription_name == "test_subscription"
        assert stream.source_db_id == "550e8400-e29b-41d4-a716-446655440000"
        assert stream.target_db_id == "550e8400-e29b-41d4-a716-446655440001"
        assert stream.status == "active"
        assert stream.is_managed is True

    @pytest.mark.asyncio
    async def test_discover_physical_replication_success(
        self, discovery_service, sample_databases, mock_connection_manager
    ):
        """Test successful physical replication discovery."""
        # Mock physical replication results
        physical_results = [
            {
                "pid": 12345,
                "usename": "testuser",
                "application_name": "walreceiver",
                "client_addr": "postgres-replica",
                "client_hostname": "postgres-replica",
                "client_port": 54321,
                "backend_start": datetime.utcnow(),
                "backend_xmin": None,
                "state": "streaming",
                "sent_lsn": "0/2000ABCD",
                "write_lsn": "0/2000ABCD",
                "flush_lsn": "0/2000ABCD",
                "replay_lsn": "0/1FFF1234",
                "write_lag": None,
                "flush_lag": None,
                "replay_lag": None,
                "sync_priority": 0,
                "sync_state": "async",
                "reply_time": datetime.utcnow(),
            }
        ]

        # Mock connection manager methods
        from app.services.postgres_connection import ConnectionHealth
        mock_health = ConnectionHealth(
            is_healthy=False,
            last_check=datetime.utcnow(),
            error_message="Not connected"
        )
        mock_connection_manager.get_health_status.return_value = mock_health
        mock_connection_manager.add_database = AsyncMock()

        # Configure mock response
        def mock_execute_query(db_id, query, *args):
            if "pg_stat_replication" in query:
                return physical_results
            else:
                return []
        
        mock_connection_manager.execute_query.side_effect = mock_execute_query

        # Execute discovery
        streams = await discovery_service.discover_physical_replication(sample_databases)

        # Verify results
        assert len(streams) == 1
        stream = streams[0]
        assert stream.type == "physical"
        assert stream.wal_sender_pid == 12345
        assert stream.source_db_id == "550e8400-e29b-41d4-a716-446655440000"
        assert stream.target_db_id == "550e8400-e29b-41d4-a716-446655440001"  # Matched by client_addr
        assert stream.status == "active"
        assert stream.is_managed is False

    @pytest.mark.asyncio
    async def test_collect_logical_metrics_success(
        self, discovery_service, mock_connection_manager
    ):
        """Test successful logical replication metrics collection."""
        # Create test stream
        stream = ReplicationStream(
            source_db_id="550e8400-e29b-41d4-a716-446655440000",
            target_db_id="550e8400-e29b-41d4-a716-446655440001",
            type="logical",
            publication_name="test_publication",
            subscription_name="test_subscription",
            status="active",
        )

        # Mock metrics query results
        metrics_results = [
            {
                "received_lsn": "0/1234ABCD",
                "last_msg_send_time": datetime.utcnow(),
                "last_msg_receipt_time": datetime.utcnow(),
                "latest_end_lsn": "0/1234ABCD",
                "latest_end_time": datetime.utcnow(),
                "synced_tables": 4,
                "total_tables": 5,
            }
        ]

        mock_connection_manager.execute_query.return_value = metrics_results

        # Execute metrics collection
        metrics = await discovery_service.collect_replication_metrics(stream)

        # Verify results
        assert isinstance(metrics, ReplicationMetrics)
        assert metrics.stream_id == stream.id
        assert metrics.wal_position == "0/1234ABCD"
        assert metrics.synced_tables == 4
        assert metrics.total_tables == 5
        assert metrics.backfill_progress == 80.0  # 4/5 * 100

    @pytest.mark.asyncio
    async def test_collect_physical_metrics_success(
        self, discovery_service, mock_connection_manager
    ):
        """Test successful physical replication metrics collection."""
        # Create test stream
        stream = ReplicationStream(
            source_db_id="550e8400-e29b-41d4-a716-446655440000",
            target_db_id="550e8400-e29b-41d4-a716-446655440001",
            type="physical",
            wal_sender_pid=12345,
            status="active",
        )

        # Mock metrics query results
        from datetime import timedelta
        metrics_results = [
            {
                "sent_lsn": "0/2000ABCD",
                "write_lsn": "0/2000ABCD",
                "flush_lsn": "0/2000ABCD",
                "replay_lsn": "0/1FFF1234",
                "write_lag": None,
                "flush_lag": None,
                "replay_lag": timedelta(seconds=2.5),
                "state": "streaming",
            }
        ]

        mock_connection_manager.execute_query.return_value = metrics_results

        # Execute metrics collection
        metrics = await discovery_service.collect_replication_metrics(stream)

        # Verify results
        assert isinstance(metrics, ReplicationMetrics)
        assert metrics.stream_id == stream.id
        assert metrics.wal_position == "0/1FFF1234"
        assert metrics.lag_seconds == 2.5
        assert metrics.lag_bytes > 0  # Should calculate LSN difference

    @pytest.mark.asyncio
    async def test_discover_logical_replication_no_databases(self, discovery_service):
        """Test logical replication discovery with no databases."""
        streams = await discovery_service.discover_logical_replication([])
        assert streams == []

    @pytest.mark.asyncio
    async def test_discover_logical_replication_connection_error(
        self, discovery_service, sample_databases, mock_connection_manager
    ):
        """Test logical replication discovery with connection error."""
        # Mock connection error
        mock_connection_manager.execute_query.side_effect = Exception("Connection failed")

        # Execute discovery - should not raise exception but log warnings
        streams = await discovery_service.discover_logical_replication(sample_databases)
        assert streams == []

    @pytest.mark.asyncio
    async def test_collect_metrics_stream_not_found(
        self, discovery_service, mock_connection_manager
    ):
        """Test metrics collection when stream is not found."""
        # Create test stream
        stream = ReplicationStream(
            source_db_id="550e8400-e29b-41d4-a716-446655440000",
            target_db_id="550e8400-e29b-41d4-a716-446655440001",
            type="logical",
            subscription_name="nonexistent_subscription",
            status="active",
        )

        # Mock empty results
        mock_connection_manager.execute_query.return_value = []

        # Execute metrics collection - should raise exception
        with pytest.raises(ReplicationDiscoveryError, match="Subscription nonexistent_subscription not found"):
            await discovery_service.collect_replication_metrics(stream)

    @pytest.mark.asyncio
    async def test_collect_metrics_missing_subscription_name(self, discovery_service):
        """Test metrics collection with missing subscription name."""
        # Create test stream without subscription name
        stream = ReplicationStream(
            source_db_id="550e8400-e29b-41d4-a716-446655440000",
            target_db_id="550e8400-e29b-41d4-a716-446655440001",
            type="logical",
            status="active",
        )

        # Execute metrics collection - should raise exception
        with pytest.raises(ReplicationDiscoveryError, match="Subscription name required"):
            await discovery_service.collect_replication_metrics(stream)

    def test_calculate_lsn_diff_success(self, discovery_service):
        """Test LSN difference calculation."""
        # Test normal case
        lsn1 = "0/2000ABCD"
        lsn2 = "0/1FFF1234"
        diff = discovery_service._calculate_lsn_diff(lsn1, lsn2)
        assert diff > 0

        # Test same LSN
        diff = discovery_service._calculate_lsn_diff(lsn1, lsn1)
        assert diff == 0

        # Test reverse order (should return 0)
        diff = discovery_service._calculate_lsn_diff(lsn2, lsn1)
        assert diff == 0

    def test_calculate_lsn_diff_invalid_format(self, discovery_service):
        """Test LSN difference calculation with invalid format."""
        # Test invalid format
        diff = discovery_service._calculate_lsn_diff("invalid", "0/1234ABCD")
        assert diff == 0

        diff = discovery_service._calculate_lsn_diff("0/1234ABCD", "invalid")
        assert diff == 0

    @pytest.mark.asyncio
    async def test_parse_replication_errors_placeholder(self, discovery_service):
        """Test replication error parsing (placeholder implementation)."""
        errors = await discovery_service.parse_replication_errors("test-db")
        assert errors == []  # Placeholder returns empty list


class TestLogicalReplicationInfo:
    """Test cases for LogicalReplicationInfo."""

    def test_logical_replication_info_creation(self):
        """Test LogicalReplicationInfo creation."""
        info = LogicalReplicationInfo(
            publication_name="test_pub",
            subscription_name="test_sub",
            status="active",
        )
        assert info.publication_name == "test_pub"
        assert info.subscription_name == "test_sub"
        assert info.status == "active"
        assert info.lag_bytes == 0
        assert info.lag_seconds == 0.0


class TestPhysicalReplicationInfo:
    """Test cases for PhysicalReplicationInfo."""

    def test_physical_replication_info_creation(self):
        """Test PhysicalReplicationInfo creation."""
        info = PhysicalReplicationInfo(
            replication_slot_name="test_slot",
            wal_sender_pid=12345,
            status="active",
            client_addr="192.168.1.100",
        )
        assert info.replication_slot_name == "test_slot"
        assert info.wal_sender_pid == 12345
        assert info.status == "active"
        assert info.client_addr == "192.168.1.100"
        assert info.lag_bytes == 0
        assert info.lag_seconds == 0.0