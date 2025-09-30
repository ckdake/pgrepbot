"""
Replication management API endpoints.

This module provides REST API endpoints for discovering, monitoring, and managing
PostgreSQL replication streams.
"""

import logging
from datetime import datetime
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_connection_manager, get_rds_client, get_redis_client
from app.models.database import DatabaseConfig
from app.models.replication import ReplicationMetrics, ReplicationStream
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/replication", tags=["replication"])


class ReplicationDiscoveryResponse(BaseModel):
    """Response model for replication discovery."""

    logical_streams: list[ReplicationStream]
    physical_streams: list[ReplicationStream]
    total_streams: int
    discovery_timestamp: str
    errors: list[str]


class ReplicationTopologyResponse(BaseModel):
    """Response model for replication topology."""

    databases: list[DatabaseConfig]
    streams: list[ReplicationStream]
    metrics: dict[str, ReplicationMetrics]
    topology_map: dict[str, Any]
    last_updated: str


class ReplicationMetricsResponse(BaseModel):
    """Response model for replication metrics."""

    stream_id: str
    metrics: ReplicationMetrics
    collected_at: str


@router.get("/discover", response_model=ReplicationDiscoveryResponse)
async def discover_replication_topology(
    connection_manager: PostgreSQLConnectionManager = Depends(get_connection_manager),
    redis_client: redis.Redis = Depends(get_redis_client),
    rds_client=Depends(get_rds_client),
) -> ReplicationDiscoveryResponse:
    """
    Discover all replication streams across configured databases.

    This endpoint performs comprehensive discovery of both logical and physical
    replication streams by querying PostgreSQL system views and AWS RDS APIs.

    Returns:
        ReplicationDiscoveryResponse: Discovered replication streams and metadata
    """
    try:
        logger.info("Starting replication topology discovery")

        # Get configured databases from Redis
        databases = await _get_configured_databases(redis_client)
        if not databases:
            logger.warning("No databases configured for replication discovery")
            return ReplicationDiscoveryResponse(
                logical_streams=[],
                physical_streams=[],
                total_streams=0,
                discovery_timestamp=datetime.utcnow().isoformat(),
                errors=["No databases configured"],
            )

        # Initialize discovery service
        discovery_service = ReplicationDiscoveryService(
            connection_manager=connection_manager,
            rds_client=rds_client,
        )

        errors = []
        logical_streams = []
        physical_streams = []

        # Discover logical replication
        try:
            logical_streams = await discovery_service.discover_logical_replication(databases)
            logger.info(f"Discovered {len(logical_streams)} logical replication streams")
        except Exception as e:
            error_msg = f"Logical replication discovery failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Discover physical replication
        try:
            physical_streams = await discovery_service.discover_physical_replication(databases)
            logger.info(f"Discovered {len(physical_streams)} physical replication streams")
        except Exception as e:
            error_msg = f"Physical replication discovery failed: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        # Cache discovered streams in Redis
        all_streams = logical_streams + physical_streams
        await _cache_discovered_streams(redis_client, all_streams)

        total_streams = len(all_streams)
        logger.info(f"Discovery complete: {total_streams} total streams found")

        return ReplicationDiscoveryResponse(
            logical_streams=logical_streams,
            physical_streams=physical_streams,
            total_streams=total_streams,
            discovery_timestamp=datetime.utcnow().isoformat(),
            errors=errors,
        )

    except Exception as e:
        logger.error(f"Replication discovery failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Replication discovery failed: {e}",
        ) from e


@router.get("/topology", response_model=ReplicationTopologyResponse)
async def get_replication_topology(
    connection_manager: PostgreSQLConnectionManager = Depends(get_connection_manager),
    redis_client: redis.Redis = Depends(get_redis_client),
    rds_client=Depends(get_rds_client),
) -> ReplicationTopologyResponse:
    """
    Get complete replication topology with current metrics.

    This endpoint returns the full replication topology including databases,
    streams, current metrics, and a topology map for visualization.

    Returns:
        ReplicationTopologyResponse: Complete topology information
    """
    try:
        logger.info("Retrieving replication topology")

        # Get databases and streams from cache
        databases = await _get_configured_databases(redis_client)
        streams = await _get_cached_streams(redis_client)

        # Initialize discovery service for metrics collection
        discovery_service = ReplicationDiscoveryService(
            connection_manager=connection_manager,
            rds_client=rds_client,
        )

        # Collect current metrics for all streams
        metrics = {}
        for stream in streams:
            try:
                stream_metrics = await discovery_service.collect_replication_metrics(stream)
                metrics[stream.id] = stream_metrics
            except Exception as e:
                logger.warning(f"Failed to collect metrics for stream {stream.id}: {e}")

        # Build topology map for visualization
        topology_map = _build_topology_map(databases, streams, metrics)

        return ReplicationTopologyResponse(
            databases=databases,
            streams=streams,
            metrics=metrics,
            topology_map=topology_map,
            last_updated=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to get replication topology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get replication topology: {e}",
        ) from e


@router.get("/streams/{stream_id}/metrics", response_model=ReplicationMetricsResponse)
async def get_stream_metrics(
    stream_id: str,
    connection_manager: PostgreSQLConnectionManager = Depends(get_connection_manager),
    redis_client: redis.Redis = Depends(get_redis_client),
    rds_client=Depends(get_rds_client),
) -> ReplicationMetricsResponse:
    """
    Get current metrics for a specific replication stream.

    Args:
        stream_id: Replication stream identifier

    Returns:
        ReplicationMetricsResponse: Current stream metrics
    """
    try:
        logger.info(f"Collecting metrics for stream {stream_id}")

        # Get stream from cache
        streams = await _get_cached_streams(redis_client)
        stream = next((s for s in streams if s.id == stream_id), None)

        if not stream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Replication stream {stream_id} not found",
            )

        # Initialize discovery service
        discovery_service = ReplicationDiscoveryService(
            connection_manager=connection_manager,
            rds_client=rds_client,
        )

        # Collect current metrics
        metrics = await discovery_service.collect_replication_metrics(stream)

        return ReplicationMetricsResponse(
            stream_id=stream_id,
            metrics=metrics,
            collected_at=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to collect metrics for stream {stream_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to collect stream metrics: {e}",
        ) from e


@router.post("/refresh")
async def refresh_replication_discovery(
    connection_manager: PostgreSQLConnectionManager = Depends(get_connection_manager),
    redis_client: redis.Redis = Depends(get_redis_client),
    rds_client=Depends(get_rds_client),
) -> dict[str, Any]:
    """
    Refresh replication discovery and update cached data.

    This endpoint triggers a fresh discovery of all replication streams
    and updates the cached topology information.

    Returns:
        dict: Refresh operation results
    """
    try:
        logger.info("Refreshing replication discovery")

        # Perform fresh discovery
        discovery_response = await discover_replication_topology(
            connection_manager=connection_manager,
            redis_client=redis_client,
            rds_client=rds_client,
        )

        return {
            "success": True,
            "message": "Replication discovery refreshed successfully",
            "total_streams": discovery_response.total_streams,
            "logical_streams": len(discovery_response.logical_streams),
            "physical_streams": len(discovery_response.physical_streams),
            "errors": discovery_response.errors,
            "refreshed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to refresh replication discovery: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh replication discovery: {e}",
        ) from e


async def _get_configured_databases(redis_client: redis.Redis) -> list[DatabaseConfig]:
    """Get configured databases from Redis cache."""
    try:
        # Get all database configuration keys
        keys = await redis_client.keys("database:*")
        databases = []

        for key in keys:
            try:
                data = await redis_client.get(key)
                if data:
                    db_config = DatabaseConfig.model_validate_json(data)
                    databases.append(db_config)
            except Exception as e:
                logger.warning(f"Failed to parse database config from {key}: {e}")

        logger.info(f"Found {len(databases)} configured databases")
        return databases

    except Exception as e:
        logger.error(f"Failed to get configured databases: {e}")
        return []


async def _get_cached_streams(redis_client: redis.Redis) -> list[ReplicationStream]:
    """Get cached replication streams from Redis."""
    try:
        # Get all replication stream keys
        keys = await redis_client.keys("replication_stream:*")
        streams = []

        for key in keys:
            try:
                data = await redis_client.get(key)
                if data:
                    stream = ReplicationStream.model_validate_json(data)
                    streams.append(stream)
            except Exception as e:
                logger.warning(f"Failed to parse replication stream from {key}: {e}")

        return streams

    except Exception as e:
        logger.error(f"Failed to get cached streams: {e}")
        return []


async def _cache_discovered_streams(redis_client: redis.Redis, streams: list[ReplicationStream]) -> None:
    """Cache discovered replication streams in Redis."""
    try:
        # Clear existing stream cache
        existing_keys = await redis_client.keys("replication_stream:*")
        if existing_keys:
            await redis_client.delete(*existing_keys)

        # Cache new streams
        for stream in streams:
            key = f"replication_stream:{stream.id}"
            await redis_client.set(key, stream.model_dump_json(), ex=3600)  # 1 hour TTL

        logger.info(f"Cached {len(streams)} replication streams")

    except Exception as e:
        logger.error(f"Failed to cache discovered streams: {e}")


def _build_topology_map(
    databases: list[DatabaseConfig],
    streams: list[ReplicationStream],
    metrics: dict[str, ReplicationMetrics],
) -> dict[str, Any]:
    """
    Build topology map for visualization.

    Args:
        databases: List of database configurations
        streams: List of replication streams
        metrics: Current metrics for streams

    Returns:
        Topology map with nodes and edges for visualization
    """
    # Build nodes (databases)
    nodes = []
    for db in databases:
        node = {
            "id": db.id,
            "name": db.name,
            "type": "database",
            "role": db.role,
            "host": db.host,
            "port": db.port,
            "environment": db.environment,
            "cloud_provider": db.cloud_provider,
            "status": "unknown",  # Would be determined by connection health
        }
        nodes.append(node)

    # Build edges (replication streams)
    edges = []
    for stream in streams:
        # Get current metrics if available
        stream_metrics = metrics.get(stream.id)

        edge = {
            "id": stream.id,
            "source": stream.source_db_id,
            "target": stream.target_db_id,
            "type": stream.type,
            "status": stream.status,
            "lag_bytes": stream_metrics.lag_bytes if stream_metrics else stream.lag_bytes,
            "lag_seconds": stream_metrics.lag_seconds if stream_metrics else stream.lag_seconds,
            "is_managed": stream.is_managed,
        }

        # Add type-specific information
        if stream.type == "logical":
            edge.update(
                {
                    "publication_name": stream.publication_name,
                    "subscription_name": stream.subscription_name,
                }
            )
        else:
            edge.update(
                {
                    "replication_slot_name": stream.replication_slot_name,
                    "wal_sender_pid": stream.wal_sender_pid,
                }
            )

        edges.append(edge)

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "total_databases": len(databases),
            "total_streams": len(streams),
            "logical_streams": len([s for s in streams if s.type == "logical"]),
            "physical_streams": len([s for s in streams if s.type == "physical"]),
            "active_streams": len([s for s in streams if s.status == "active"]),
        },
    }
