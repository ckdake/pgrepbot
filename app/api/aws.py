"""
AWS integration API endpoints.

This module provides API endpoints for testing and demonstrating AWS service
integrations including Secrets Manager, ElastiCache, and RDS.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.aws_elasticache import ElastiCacheManager
from app.services.aws_rds import RDSClient, RDSError
from app.services.aws_secrets import SecretsManagerClient, SecretsManagerError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aws", tags=["AWS Integration"])


class AWSTestResponse(BaseModel):
    """Response model for AWS integration tests."""

    service: str
    status: str
    message: str
    data: dict[str, Any] = {}
    error: str = ""


class AWSIntegrationStatus(BaseModel):
    """Response model for overall AWS integration status."""

    secrets_manager: AWSTestResponse
    elasticache: AWSTestResponse
    rds: AWSTestResponse
    overall_status: str


@router.get("/test", response_model=AWSIntegrationStatus)
async def test_aws_integrations():
    """
    Test all AWS service integrations.

    This endpoint tests connectivity and basic operations for:
    - AWS Secrets Manager
    - ElastiCache Redis
    - RDS service discovery

    Returns comprehensive status information for all services.
    """
    logger.info("Testing AWS service integrations")

    # Get configuration from environment
    aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))

    # Test results
    secrets_result = await _test_secrets_manager(aws_endpoint)
    elasticache_result = await _test_elasticache(redis_host, redis_port)
    rds_result = await _test_rds(aws_endpoint)

    # Determine overall status
    all_services = [secrets_result, elasticache_result, rds_result]
    overall_status = "healthy" if all(s.status == "healthy" for s in all_services) else "degraded"

    return AWSIntegrationStatus(
        secrets_manager=secrets_result,
        elasticache=elasticache_result,
        rds=rds_result,
        overall_status=overall_status,
    )


@router.get("/secrets/test", response_model=AWSTestResponse)
async def test_secrets_manager():
    """Test AWS Secrets Manager integration."""
    aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
    return await _test_secrets_manager(aws_endpoint)


@router.get("/elasticache/test", response_model=AWSTestResponse)
async def test_elasticache():
    """Test ElastiCache Redis integration."""
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    return await _test_elasticache(redis_host, redis_port)


@router.get("/rds/test", response_model=AWSTestResponse)
async def test_rds():
    """Test RDS service integration."""
    aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
    return await _test_rds(aws_endpoint)


@router.get("/secrets/{secret_name:path}")
async def get_secret(secret_name: str):
    """
    Retrieve a secret from AWS Secrets Manager.

    Args:
        secret_name: Name or ARN of the secret to retrieve

    Returns:
        Secret data (sensitive fields masked)
    """
    try:
        aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
        secrets_client = SecretsManagerClient(endpoint_url=aws_endpoint)

        secret_data = await secrets_client.get_secret(secret_name)

        # Mask sensitive fields for API response
        masked_data = {}
        for key, value in secret_data.items():
            if any(sensitive in key.lower() for sensitive in ["password", "secret", "key", "token"]):
                masked_data[key] = "***MASKED***"
            else:
                masked_data[key] = value

        return {
            "secret_name": secret_name,
            "data": masked_data,
            "cache_info": secrets_client.get_cache_info(),
        }

    except SecretsManagerError as e:
        logger.error(f"Secrets Manager error retrieving {secret_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve secret: {e}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error retrieving secret {secret_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@router.get("/rds/instances")
async def list_rds_instances():
    """List all RDS instances in the region."""
    try:
        aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
        rds_client = RDSClient(endpoint_url=aws_endpoint)

        instances = await rds_client.list_db_instances()
        return {
            "total_instances": len(instances),
            "instances": instances,
        }

    except RDSError as e:
        logger.error(f"RDS error listing instances: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list RDS instances: {e}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error listing RDS instances: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@router.get("/rds/topology")
async def get_replication_topology():
    """Discover and return RDS replication topology."""
    try:
        aws_endpoint = os.getenv("AWS_ENDPOINT_URL")
        rds_client = RDSClient(endpoint_url=aws_endpoint)

        topology = await rds_client.discover_replication_topology()
        return topology

    except RDSError as e:
        logger.error(f"RDS error discovering topology: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to discover replication topology: {e}",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error discovering topology: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


async def _test_secrets_manager(endpoint_url: str = None) -> AWSTestResponse:
    """Test Secrets Manager connectivity and operations."""
    try:
        secrets_client = SecretsManagerClient(endpoint_url=endpoint_url)

        # Test basic connectivity by trying to get a test secret
        test_secret_name = "test/database/credentials"

        try:
            # Try to get a test secret (this may fail if it doesn't exist)
            await secrets_client.get_secret(test_secret_name)
            message = "Successfully connected and retrieved test secret"
            data = secrets_client.get_cache_info()
        except SecretsManagerError as e:
            if "not found" in str(e).lower():
                message = "Connected successfully (test secret not found, which is expected)"
                data = {"note": "Connection test passed, no test secrets configured"}
            else:
                raise e

        return AWSTestResponse(
            service="secrets_manager",
            status="healthy",
            message=message,
            data=data,
        )

    except Exception as e:
        logger.error(f"Secrets Manager test failed: {e}")
        return AWSTestResponse(
            service="secrets_manager",
            status="unhealthy",
            message="Failed to connect to Secrets Manager",
            error=str(e),
        )


async def _test_elasticache(host: str, port: int) -> AWSTestResponse:
    """Test ElastiCache Redis connectivity and operations."""
    try:
        async with ElastiCacheManager(host=host, port=port) as redis_manager:
            # Test basic operations
            test_key = "aws_integration_test"
            test_value = "test_value_123"

            # Test set operation
            await redis_manager.set(test_key, test_value, ex=60)

            # Test get operation
            retrieved_value = await redis_manager.get(test_key)

            # Test info operation
            info = await redis_manager.get_info()

            # Clean up test key
            await redis_manager.delete(test_key)

            if retrieved_value == test_value:
                return AWSTestResponse(
                    service="elasticache",
                    status="healthy",
                    message="Successfully connected and performed Redis operations",
                    data={
                        "redis_version": info.get("redis_version"),
                        "connected_clients": info.get("connected_clients"),
                        "used_memory_human": info.get("used_memory_human"),
                        "test_operations": "set/get/delete successful",
                    },
                )
            else:
                return AWSTestResponse(
                    service="elasticache",
                    status="unhealthy",
                    message="Redis operations failed - data integrity issue",
                    error=f"Expected {test_value}, got {retrieved_value}",
                )

    except Exception as e:
        logger.error(f"ElastiCache test failed: {e}")
        return AWSTestResponse(
            service="elasticache",
            status="unhealthy",
            message="Failed to connect to ElastiCache Redis",
            error=str(e),
        )


async def _test_rds(endpoint_url: str = None) -> AWSTestResponse:
    """Test RDS service connectivity and operations."""
    try:
        # Test direct PostgreSQL connections instead of LocalStack RDS
        import asyncpg

        # Test connection to primary database
        primary_conn = None
        replica_conn = None
        primary_status = "unhealthy"
        replica_status = "unhealthy"
        primary_version = None
        replica_version = None

        try:
            # Connect to primary
            primary_conn = await asyncpg.connect(
                host="localhost", port=5432, user="testuser", password="testpass", database="testdb", command_timeout=5
            )
            primary_version = await primary_conn.fetchval("SELECT version()")
            primary_status = "healthy"

        except Exception as e:
            logger.warning(f"Primary PostgreSQL connection failed: {e}")
        finally:
            if primary_conn:
                await primary_conn.close()

        try:
            # Connect to replica
            replica_conn = await asyncpg.connect(
                host="localhost", port=5433, user="testuser", password="testpass", database="testdb", command_timeout=5
            )
            replica_version = await replica_conn.fetchval("SELECT version()")
            replica_status = "healthy"

        except Exception as e:
            logger.warning(f"Replica PostgreSQL connection failed: {e}")
        finally:
            if replica_conn:
                await replica_conn.close()

        # Determine overall status
        if primary_status == "healthy" and replica_status == "healthy":
            status = "healthy"
            message = "Successfully connected to both PostgreSQL instances"
        elif primary_status == "healthy" or replica_status == "healthy":
            status = "degraded"
            message = "Connected to some PostgreSQL instances"
        else:
            status = "unhealthy"
            message = "Failed to connect to PostgreSQL instances"

        return AWSTestResponse(
            service="rds",
            status=status,
            message=message,
            data={
                "postgres_primary": {
                    "host": "localhost:5432",
                    "status": primary_status,
                    "version": primary_version.split()[1] if primary_version else None,
                },
                "postgres_replica": {
                    "host": "localhost:5433",
                    "status": replica_status,
                    "version": replica_version.split()[1] if replica_version else None,
                },
                "note": "Direct PostgreSQL connections (Docker Compose setup)",
            },
        )

    except Exception as e:
        logger.error(f"RDS test failed: {e}")
        return AWSTestResponse(
            service="rds",
            status="unhealthy",
            message="Failed to test PostgreSQL connections",
            error=str(e),
        )
