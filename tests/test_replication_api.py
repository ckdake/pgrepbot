"""
Tests for replication API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import DatabaseConfig
from app.models.replication import ReplicationMetrics, ReplicationStream


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


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
def sample_streams():
    """Sample replication streams."""
    return [
        ReplicationStream(
            id="stream-1",
            source_db_id="550e8400-e29b-41d4-a716-446655440000",
            target_db_id="550e8400-e29b-41d4-a716-446655440001",
            type="logical",
            publication_name="test_publication",
            subscription_name="test_subscription",
            status="active",
            lag_bytes=1024,
            lag_seconds=2.5,
            is_managed=True,
        ),
        ReplicationStream(
            id="stream-2",
            source_db_id="550e8400-e29b-41d4-a716-446655440000",
            target_db_id="550e8400-e29b-41d4-a716-446655440001",
            type="physical",
            wal_sender_pid=12345,
            status="active",
            lag_bytes=512,
            lag_seconds=1.0,
            is_managed=False,
        ),
    ]


@pytest.fixture
def sample_metrics():
    """Sample replication metrics."""
    return {
        "stream-1": ReplicationMetrics(
            stream_id="550e8400-e29b-41d4-a716-446655440002",
            lag_bytes=1024,
            lag_seconds=2.5,
            wal_position="0/1234ABCD",
            synced_tables=4,
            total_tables=5,
            backfill_progress=80.0,
        ),
        "stream-2": ReplicationMetrics(
            stream_id="550e8400-e29b-41d4-a716-446655440003",
            lag_bytes=512,
            lag_seconds=1.0,
            wal_position="0/2000EFGH",
            synced_tables=0,
            total_tables=0,
        ),
    }


class TestReplicationDiscoveryEndpoint:
    """Test cases for /api/replication/discover endpoint."""

    @patch("app.api.replication._get_configured_databases")
    @patch("app.api.replication._cache_discovered_streams")
    @patch("app.api.replication.ReplicationDiscoveryService")
    def test_discover_replication_success(
        self,
        mock_discovery_service_class,
        mock_cache_streams,
        mock_get_databases,
        client,
        sample_databases,
        sample_streams,
    ):
        """Test successful replication discovery."""
        # Mock dependencies
        mock_get_databases.return_value = sample_databases
        mock_cache_streams.return_value = None

        # Mock discovery service
        mock_discovery_service = AsyncMock()
        mock_discovery_service.discover_logical_replication.return_value = [sample_streams[0]]
        mock_discovery_service.discover_physical_replication.return_value = [sample_streams[1]]
        mock_discovery_service_class.return_value = mock_discovery_service

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()

            # Make request
            response = client.get("/api/replication/discover")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert "logical_streams" in data
        assert "physical_streams" in data
        assert "total_streams" in data
        assert "discovery_timestamp" in data
        assert "errors" in data

        assert len(data["logical_streams"]) == 1
        assert len(data["physical_streams"]) == 1
        assert data["total_streams"] == 2
        assert data["logical_streams"][0]["type"] == "logical"
        assert data["physical_streams"][0]["type"] == "physical"

    @patch("app.api.replication._get_configured_databases")
    def test_discover_replication_no_databases(
        self,
        mock_get_databases,
        client,
    ):
        """Test replication discovery with no configured databases."""
        # Mock no databases
        mock_get_databases.return_value = []

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()

            # Make request
            response = client.get("/api/replication/discover")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["total_streams"] == 0
        assert len(data["errors"]) == 1
        assert "No databases configured" in data["errors"][0]

    @patch("app.api.replication._get_configured_databases")
    @patch("app.api.replication.ReplicationDiscoveryService")
    def test_discover_replication_partial_failure(
        self,
        mock_discovery_service_class,
        mock_get_databases,
        client,
        sample_databases,
        sample_streams,
    ):
        """Test replication discovery with partial failures."""
        # Mock dependencies
        mock_get_databases.return_value = sample_databases

        # Mock discovery service with one failure
        mock_discovery_service = AsyncMock()
        mock_discovery_service.discover_logical_replication.return_value = [sample_streams[0]]
        mock_discovery_service.discover_physical_replication.side_effect = Exception("Physical discovery failed")
        mock_discovery_service_class.return_value = mock_discovery_service

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
            patch("app.api.replication._cache_discovered_streams") as mock_cache,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()
            mock_cache.return_value = None

            # Make request
            response = client.get("/api/replication/discover")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert len(data["logical_streams"]) == 1
        assert len(data["physical_streams"]) == 0
        assert data["total_streams"] == 1
        assert len(data["errors"]) == 1
        assert "Physical replication discovery failed" in data["errors"][0]


class TestReplicationTopologyEndpoint:
    """Test cases for /api/replication/topology endpoint."""

    @patch("app.api.replication._get_configured_databases")
    @patch("app.api.replication._get_cached_streams")
    @patch("app.api.replication.ReplicationDiscoveryService")
    def test_get_topology_success(
        self,
        mock_discovery_service_class,
        mock_get_streams,
        mock_get_databases,
        client,
        sample_databases,
        sample_streams,
        sample_metrics,
    ):
        """Test successful topology retrieval."""
        # Mock dependencies
        mock_get_databases.return_value = sample_databases
        mock_get_streams.return_value = sample_streams

        # Mock discovery service for metrics collection
        mock_discovery_service = AsyncMock()
        mock_discovery_service.collect_replication_metrics.side_effect = [
            sample_metrics["stream-1"],
            sample_metrics["stream-2"],
        ]
        mock_discovery_service_class.return_value = mock_discovery_service

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()

            # Make request
            response = client.get("/api/replication/topology")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert "databases" in data
        assert "streams" in data
        assert "metrics" in data
        assert "topology_map" in data
        assert "last_updated" in data

        assert len(data["databases"]) == 2
        assert len(data["streams"]) == 2
        assert len(data["metrics"]) == 2

        # Verify topology map structure
        topology_map = data["topology_map"]
        assert "nodes" in topology_map
        assert "edges" in topology_map
        assert "summary" in topology_map

        assert len(topology_map["nodes"]) == 2
        assert len(topology_map["edges"]) == 2
        assert topology_map["summary"]["total_databases"] == 2
        assert topology_map["summary"]["total_streams"] == 2


class TestStreamMetricsEndpoint:
    """Test cases for /api/replication/streams/{stream_id}/metrics endpoint."""

    @patch("app.api.replication._get_cached_streams")
    @patch("app.api.replication.ReplicationDiscoveryService")
    def test_get_stream_metrics_success(
        self,
        mock_discovery_service_class,
        mock_get_streams,
        client,
        sample_streams,
        sample_metrics,
    ):
        """Test successful stream metrics retrieval."""
        # Mock dependencies
        mock_get_streams.return_value = sample_streams

        # Mock discovery service
        mock_discovery_service = AsyncMock()
        mock_discovery_service.collect_replication_metrics.return_value = sample_metrics["stream-1"]
        mock_discovery_service_class.return_value = mock_discovery_service

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()

            # Make request
            response = client.get("/api/replication/streams/stream-1/metrics")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["stream_id"] == "stream-1"
        assert "metrics" in data
        assert "collected_at" in data

        metrics = data["metrics"]
        assert metrics["lag_bytes"] == 1024
        assert metrics["lag_seconds"] == 2.5
        assert metrics["wal_position"] == "0/1234ABCD"

    @patch("app.api.replication._get_cached_streams")
    def test_get_stream_metrics_not_found(
        self,
        mock_get_streams,
        client,
        sample_streams,
    ):
        """Test stream metrics retrieval for non-existent stream."""
        # Mock dependencies
        mock_get_streams.return_value = sample_streams

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()

            # Make request for non-existent stream
            response = client.get("/api/replication/streams/nonexistent-stream/metrics")

        # Verify response
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestRefreshEndpoint:
    """Test cases for /api/replication/refresh endpoint."""

    @patch("app.api.replication.discover_replication_topology")
    def test_refresh_success(
        self,
        mock_discover,
        client,
    ):
        """Test successful replication refresh."""
        # Mock discovery response
        mock_discover.return_value = MagicMock(
            total_streams=2,
            logical_streams=[MagicMock()],
            physical_streams=[MagicMock()],
            errors=[],
        )

        # Mock dependencies
        with (
            patch("app.api.replication.get_connection_manager") as mock_conn_mgr,
            patch("app.api.replication.get_redis_client") as mock_redis,
            patch("app.api.replication.get_rds_client") as mock_rds,
        ):
            mock_conn_mgr.return_value = AsyncMock()
            mock_redis.return_value = AsyncMock()
            mock_rds.return_value = AsyncMock()

            # Make request
            response = client.post("/api/replication/refresh")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "refreshed successfully" in data["message"]
        assert data["total_streams"] == 2
        assert data["logical_streams"] == 1
        assert data["physical_streams"] == 1
        assert "refreshed_at" in data


class TestHelperFunctions:
    """Test cases for helper functions."""

    @pytest.mark.asyncio
    async def test_get_configured_databases_success(self):
        """Test successful database retrieval from Redis."""
        from app.api.replication import _get_configured_databases

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = [
            "database:550e8400-e29b-41d4-a716-446655440000",
            "database:550e8400-e29b-41d4-a716-446655440001",
        ]
        mock_redis.get.side_effect = [
            '{"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Primary", "host": "localhost", "port": 5432, '
            '"database": "testdb", "credentials_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test", '
            '"role": "primary", "environment": "test", "cloud_provider": "aws"}',
            '{"id": "550e8400-e29b-41d4-a716-446655440001", "name": "Replica", "host": "localhost", "port": 5433, '
            '"database": "testdb", "credentials_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test", '
            '"role": "replica", "environment": "test", "cloud_provider": "aws"}',
        ]

        # Execute function
        databases = await _get_configured_databases(mock_redis)

        # Verify results
        assert len(databases) == 2
        assert databases[0].id == "550e8400-e29b-41d4-a716-446655440000"
        assert databases[1].id == "550e8400-e29b-41d4-a716-446655440001"

    @pytest.mark.asyncio
    async def test_get_cached_streams_success(self):
        """Test successful stream retrieval from Redis."""
        from app.api.replication import _get_cached_streams

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["replication_stream:stream-1"]
        mock_redis.get.return_value = (
            '{"id": "stream-1", "source_db_id": "550e8400-e29b-41d4-a716-446655440000", '
            '"target_db_id": "550e8400-e29b-41d4-a716-446655440001", '
            '"type": "logical", "status": "active", "lag_bytes": 0, "lag_seconds": 0.0, "is_managed": true}'
        )

        # Execute function
        streams = await _get_cached_streams(mock_redis)

        # Verify results
        assert len(streams) == 1
        assert streams[0].id == "stream-1"
        assert streams[0].type == "logical"

    def test_build_topology_map(self, sample_databases, sample_streams, sample_metrics):
        """Test topology map building."""
        from app.api.replication import _build_topology_map

        # Execute function
        topology_map = _build_topology_map(sample_databases, sample_streams, sample_metrics)

        # Verify structure
        assert "nodes" in topology_map
        assert "edges" in topology_map
        assert "summary" in topology_map

        # Verify nodes
        nodes = topology_map["nodes"]
        assert len(nodes) == 2
        assert all(node["type"] == "database" for node in nodes)
        assert any(node["role"] == "primary" for node in nodes)
        assert any(node["role"] == "replica" for node in nodes)

        # Verify edges
        edges = topology_map["edges"]
        assert len(edges) == 2
        assert any(edge["type"] == "logical" for edge in edges)
        assert any(edge["type"] == "physical" for edge in edges)

        # Verify summary
        summary = topology_map["summary"]
        assert summary["total_databases"] == 2
        assert summary["total_streams"] == 2
        assert summary["logical_streams"] == 1
        assert summary["physical_streams"] == 1
