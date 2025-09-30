"""
Database connection API endpoints.

This module provides API endpoints for testing and managing PostgreSQL database
connections with health monitoring and connection pool statistics.
"""

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.aws_rds import RDSClient
from app.services.aws_secrets import SecretsManagerClient
from app.services.postgres_connection import (
    PostgreSQLConnectionError,
    PostgreSQLConnectionManager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/databases", tags=["Database Connections"])

# Global connection manager instance
_connection_manager: PostgreSQLConnectionManager | None = None


class DatabaseTestResponse(BaseModel):
    """Response model for database connection tests."""

    database_id: str
    status: str
    message: str
    data: dict[str, Any] = {}
    error: str = ""


class DatabaseHealthResponse(BaseModel):
    """Response model for database health status."""

    database_id: str
    is_healthy: bool
    last_check: str
    error_message: str | None = None
    response_time_ms: float | None = None
    server_version: str | None = None


class DatabaseConnectionStatus(BaseModel):
    """Response model for overall database connection status."""

    total_databases: int
    healthy_databases: int
    databases: list[DatabaseHealthResponse]
    pool_stats: dict[str, dict[str, Any]]
    overall_status: str


async def get_connection_manager() -> PostgreSQLConnectionManager:
    """Get or create the global connection manager."""
    global _connection_manager

    if _connection_manager is None:
        # Initialize AWS clients
        aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
        secrets_client = SecretsManagerClient(endpoint_url=aws_endpoint)
        rds_client = RDSClient(endpoint_url=aws_endpoint)

        _connection_manager = PostgreSQLConnectionManager(
            secrets_client=secrets_client,
            rds_client=rds_client,
            pool_min_size=1,
            pool_max_size=5,  # Smaller pools for testing
            health_check_interval=30,
        )

        # Add test databases
        await _add_test_databases(_connection_manager)

    return _connection_manager


async def _add_test_databases(manager: PostgreSQLConnectionManager) -> None:
    """Add test databases from Redis configuration to the connection manager."""
    try:
        # Import here to avoid circular imports
        from app.api.replication import _get_configured_databases
        from app.dependencies import get_redis_client

        # Get Redis client and configured databases
        redis_client = await get_redis_client()
        databases = await _get_configured_databases(redis_client)

        logger.info(f"Found {len(databases)} configured databases in Redis")

        # Add each database to the connection manager
        for db in databases:
            try:
                await manager.add_database(
                    db_id=db.id,
                    host=db.host,
                    port=db.port,
                    database=db.database,
                    secrets_arn=db.credentials_arn,
                    use_iam_auth=db.use_iam_auth,
                )
                logger.info(f"Added database {db.name} ({db.id}) to connection manager")
            except Exception as db_error:
                logger.error(f"Failed to add database {db.name}: {db_error}")

    except Exception as e:
        logger.error(f"Failed to add test databases: {e}")
        # Fallback to hardcoded databases if Redis configuration fails
        logger.info("Falling back to hardcoded database configuration")
        try:
            # Add primary database
            await manager.add_database(
                db_id="primary-fallback",
                host="localhost",
                port=5432,
                database="testdb",
                username="testuser",
                password="testpass",
            )

            # Add replica database
            await manager.add_database(
                db_id="replica-fallback",
                host="localhost",
                port=5433,
                database="testdb",
                username="testuser",
                password="testpass",
            )
            logger.info("Added fallback databases to connection manager")
        except Exception as fallback_error:
            logger.error(f"Failed to add fallback databases: {fallback_error}")


@router.get("/test", response_model=DatabaseConnectionStatus)
async def test_database_connections():
    """
    Test all database connections and return comprehensive status.

    Returns health status, connection pool statistics, and overall system status.
    """
    try:
        manager = await get_connection_manager()

        # Get health status for all databases
        health_statuses = manager.get_health_status()
        pool_stats = manager.get_pool_stats()

        # Convert health statuses to response format
        database_responses = []
        healthy_count = 0

        for db_id, health in health_statuses.items():
            if health.is_healthy:
                healthy_count += 1

            database_responses.append(
                DatabaseHealthResponse(
                    database_id=db_id,
                    is_healthy=health.is_healthy,
                    last_check=health.last_check.isoformat(),
                    error_message=health.error_message,
                    response_time_ms=health.response_time_ms,
                    server_version=health.server_version,
                )
            )

        # Determine overall status
        total_databases = len(health_statuses)
        if healthy_count == total_databases and total_databases > 0:
            overall_status = "healthy"
        elif healthy_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return DatabaseConnectionStatus(
            total_databases=total_databases,
            healthy_databases=healthy_count,
            databases=database_responses,
            pool_stats=pool_stats,
            overall_status=overall_status,
        )

    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection test failed: {e}",
        ) from e


@router.get("/test/{database_id}", response_model=DatabaseTestResponse)
async def test_single_database(database_id: str):
    """
    Test connection to a specific database.

    Args:
        database_id: Database identifier to test

    Returns:
        Detailed test results for the specified database
    """
    try:
        manager = await get_connection_manager()

        # Get health status
        health = manager.get_health_status(database_id)
        pool_stats = manager.get_pool_stats(database_id)

        if health.is_healthy:
            # Perform additional test query
            try:
                result = await manager.execute_query(
                    database_id,
                    "SELECT current_database(), current_user, inet_server_addr(), inet_server_port()",
                    timeout=5.0,
                )

                if result:
                    row = result[0]
                    test_data = {
                        "current_database": row[0],
                        "current_user": row[1],
                        "server_addr": str(row[2]) if row[2] else None,  # Convert IPv4Address to string
                        "server_port": row[3],
                        "health": health.to_dict(),
                        "pool_stats": pool_stats.get(database_id, {}),
                    }
                else:
                    test_data = {
                        "health": health.to_dict(),
                        "pool_stats": pool_stats.get(database_id, {}),
                    }

                return DatabaseTestResponse(
                    database_id=database_id,
                    status="healthy",
                    message="Database connection test successful",
                    data=test_data,
                )

            except Exception as query_error:
                return DatabaseTestResponse(
                    database_id=database_id,
                    status="degraded",
                    message="Connection available but query failed",
                    data={
                        "health": health.to_dict(),
                        "pool_stats": pool_stats.get(database_id, {}),
                    },
                    error=str(query_error),
                )
        else:
            return DatabaseTestResponse(
                database_id=database_id,
                status="unhealthy",
                message="Database connection unhealthy",
                data={
                    "health": health.to_dict(),
                    "pool_stats": pool_stats.get(database_id, {}),
                },
                error=health.error_message or "Unknown error",
            )

    except Exception as e:
        logger.error(f"Database test failed for {database_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database test failed: {e}",
        ) from e


@router.get("/health")
async def get_database_health():
    """Get health status for all databases."""
    try:
        manager = await get_connection_manager()
        health_statuses = manager.get_health_status()

        return {
            "databases": {db_id: health.to_dict() for db_id, health in health_statuses.items()},
            "timestamp": health_statuses[list(health_statuses.keys())[0]].last_check.isoformat()
            if health_statuses
            else None,
        }

    except Exception as e:
        logger.error(f"Failed to get database health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database health: {e}",
        ) from e


@router.get("/pools")
async def get_pool_statistics():
    """Get connection pool statistics for all databases."""
    try:
        manager = await get_connection_manager()
        pool_stats = manager.get_pool_stats()

        return {
            "pools": pool_stats,
            "total_pools": len(pool_stats),
        }

    except Exception as e:
        logger.error(f"Failed to get pool statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pool statistics: {e}",
        ) from e


@router.post("/query/{database_id}")
async def execute_test_query(database_id: str, query: str):
    """
    Execute a test query on the specified database.

    Args:
        database_id: Database identifier
        query: SQL query to execute (SELECT queries only for safety)

    Returns:
        Query results
    """
    # Safety check - only allow SELECT queries
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only SELECT queries are allowed for safety",
        )

    try:
        manager = await get_connection_manager()

        result = await manager.execute_query(database_id, query, timeout=10.0)

        # Convert result to JSON-serializable format
        if result:
            rows = []
            for row in result:
                # Convert asyncpg.Record to dict
                row_dict = dict(row)
                rows.append(row_dict)

            return {
                "database_id": database_id,
                "query": query,
                "row_count": len(rows),
                "rows": rows,
            }
        else:
            return {
                "database_id": database_id,
                "query": query,
                "row_count": 0,
                "rows": [],
            }

    except PostgreSQLConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution failed: {e}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error executing query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@router.post("/reset")
async def reset_connection_manager():
    """Reset the connection manager to pick up new database configurations."""
    global _connection_manager

    if _connection_manager:
        await _connection_manager.close_all()
        _connection_manager = None

    return {"message": "Connection manager reset successfully"}


@router.post("/reload")
async def reload_database_connections():
    """
    Reload database connections from Redis configuration.

    This endpoint clears the current connection manager and reinitializes it
    with the latest database configurations from Redis. Useful for picking up
    configuration changes without restarting the application.
    """
    global _connection_manager

    try:
        logger.info("Reloading database connections...")

        # Close existing connection manager if it exists
        if _connection_manager:
            logger.info("Closing existing connection manager...")
            await _connection_manager.close_all()
            _connection_manager = None

        # Force recreation of connection manager with fresh config
        logger.info("Creating new connection manager...")
        manager = await get_connection_manager()

        # Get health status to verify connections
        health_statuses = manager.get_health_status()
        pool_stats = manager.get_pool_stats()

        # Count healthy databases
        healthy_count = sum(1 for health in health_statuses.values() if health.is_healthy)

        return {
            "success": True,
            "message": "Database connections reloaded successfully",
            "total_databases": len(health_statuses),
            "healthy_databases": healthy_count,
            "databases": list(health_statuses.keys()),
            "pool_stats": dict(pool_stats.items()),
            "reloaded_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to reload database connections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload database connections: {e}",
        ) from e


@router.post("/clear-cache")
async def clear_connection_cache():
    """
    Clear all cached connections and force fresh connections.

    This is more aggressive than reload - it completely destroys the connection
    manager and forces everything to be recreated from scratch.
    """
    global _connection_manager

    try:
        logger.info("Clearing connection cache...")

        if _connection_manager:
            await _connection_manager.close_all()
            _connection_manager = None

        return {
            "success": True,
            "message": "Connection cache cleared successfully",
            "cleared_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to clear connection cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear connection cache: {e}",
        ) from e


@router.get("/credentials/test")
async def test_credential_resolution():
    """Test credential resolution from Secrets Manager."""
    try:
        aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
        secrets_client = SecretsManagerClient(endpoint_url=aws_endpoint)

        # Test resolving credentials for primary database
        try:
            primary_creds = await secrets_client.get_database_credentials("primary-db-creds")
            primary_status = "success"
            primary_error = None
        except Exception as e:
            primary_status = "failed"
            primary_error = str(e)
            primary_creds = None

        # Test resolving credentials for logical replica database
        try:
            replica_creds = await secrets_client.get_database_credentials("replica-db-creds")
            replica_status = "success"
            replica_error = None
        except Exception as e:
            replica_status = "failed"
            replica_error = str(e)
            replica_creds = None

        # Test resolving credentials for physical replica database
        try:
            physical_replica_creds = await secrets_client.get_database_credentials("physical-replica-db-creds")
            physical_replica_status = "success"
            physical_replica_error = None
        except Exception as e:
            physical_replica_status = "failed"
            physical_replica_error = str(e)
            physical_replica_creds = None

        return {
            "primary_database": {
                "secret_name": "primary-db-creds",
                "status": primary_status,
                "error": primary_error,
                "credentials": {
                    "host": primary_creds["host"] if primary_creds else None,
                    "port": primary_creds["port"] if primary_creds else None,
                    "database": primary_creds["dbname"] if primary_creds else None,
                    "username": primary_creds["username"] if primary_creds else None,
                    "password": "***MASKED***" if primary_creds else None,
                }
                if primary_creds
                else None,
            },
            "logical_replica_database": {
                "secret_name": "replica-db-creds",
                "status": replica_status,
                "error": replica_error,
                "credentials": {
                    "host": replica_creds["host"] if replica_creds else None,
                    "port": replica_creds["port"] if replica_creds else None,
                    "database": replica_creds["dbname"] if replica_creds else None,
                    "username": replica_creds["username"] if replica_creds else None,
                    "password": "***MASKED***" if replica_creds else None,
                }
                if replica_creds
                else None,
            },
            "physical_replica_database": {
                "secret_name": "physical-replica-db-creds",
                "status": physical_replica_status,
                "error": physical_replica_error,
                "credentials": {
                    "host": physical_replica_creds["host"] if physical_replica_creds else None,
                    "port": physical_replica_creds["port"] if physical_replica_creds else None,
                    "database": physical_replica_creds["dbname"] if physical_replica_creds else None,
                    "username": physical_replica_creds["username"] if physical_replica_creds else None,
                    "password": "***MASKED***" if physical_replica_creds else None,
                }
                if physical_replica_creds
                else None,
            },
        }

    except Exception as e:
        logger.error(f"Credential resolution test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Credential resolution test failed: {e}",
        ) from e
