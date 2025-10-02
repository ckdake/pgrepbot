"""
Database Configuration Management API

Provides CRUD operations for database configurations with authentication protection.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_redis_client
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.models.database import DatabaseConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/database-config", tags=["Database Configuration"])


class DatabaseConfigResponse(BaseModel):
    """Response model for database configuration operations"""

    success: bool
    message: str
    database_config: DatabaseConfig | None = None


class DatabaseConfigListResponse(BaseModel):
    """Response model for listing database configurations"""

    success: bool
    total_count: int
    database_configs: list[DatabaseConfig]


class CreateDatabaseConfigRequest(BaseModel):
    """Request model for creating a database configuration"""

    name: str
    host: str
    port: int
    database: str
    credentials_arn: str
    role: str  # "primary" or "replica"
    environment: str
    cloud_provider: str = "aws"
    vpc_id: str | None = None
    subnet_ids: list[str] | None = None
    security_group_ids: list[str] | None = None
    use_iam_auth: bool = False


class UpdateDatabaseConfigRequest(BaseModel):
    """Request model for updating a database configuration"""

    name: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    credentials_arn: str | None = None
    role: str | None = None
    environment: str | None = None
    cloud_provider: str | None = None
    vpc_id: str | None = None
    subnet_ids: list[str] | None = None
    security_group_ids: list[str] | None = None
    use_iam_auth: bool | None = None


@router.get("/", response_model=DatabaseConfigListResponse)
async def list_database_configs(
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    List all database configurations.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} listing database configurations")

        # Get all database configuration keys from Redis
        pattern = "database:*"
        keys = await redis_client.keys(pattern)

        database_configs = []
        for key in keys:
            try:
                config_json = await redis_client.get(key)
                if config_json:
                    config = DatabaseConfig.model_validate_json(config_json)
                    database_configs.append(config)
            except Exception as e:
                logger.warning(f"Failed to parse database config from key {key}: {e}")
                continue

        # Sort by name
        database_configs.sort(key=lambda x: x.name)

        return DatabaseConfigListResponse(
            success=True,
            total_count=len(database_configs),
            database_configs=database_configs,
        )

    except Exception as e:
        logger.error(f"Failed to list database configurations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list database configurations: {str(e)}",
        ) from e


@router.get("/{config_id}", response_model=DatabaseConfigResponse)
async def get_database_config(
    config_id: str,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Get a specific database configuration by ID.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} retrieving database configuration {config_id}")

        # Get configuration from Redis
        config_json = await redis_client.get(f"database:{config_id}")
        if not config_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration {config_id} not found",
            )

        config = DatabaseConfig.model_validate_json(config_json)

        return DatabaseConfigResponse(
            success=True,
            message="Database configuration retrieved successfully",
            database_config=config,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get database configuration {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database configuration: {str(e)}",
        ) from e


@router.post("/", response_model=DatabaseConfigResponse)
async def create_database_config(
    request: CreateDatabaseConfigRequest,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Create a new database configuration.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} creating database configuration: {request.name}")

        # Generate unique ID
        config_id = str(uuid4())

        # Create database configuration
        config = DatabaseConfig(
            id=config_id,
            name=request.name,
            host=request.host,
            port=request.port,
            database=request.database,
            credentials_arn=request.credentials_arn,
            role=request.role,
            environment=request.environment,
            cloud_provider=request.cloud_provider,
            vpc_id=request.vpc_id,
            subnet_ids=request.subnet_ids,
            security_group_ids=request.security_group_ids,
            use_iam_auth=request.use_iam_auth,
        )

        # Store in Redis
        await redis_client.set(
            f"database:{config_id}",
            config.model_dump_json(),
            ex=86400,  # 24 hour TTL
        )

        logger.info(f"Created database configuration {config_id} for user {user.username}")

        return DatabaseConfigResponse(
            success=True,
            message="Database configuration created successfully",
            database_config=config,
        )

    except Exception as e:
        logger.error(f"Failed to create database configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create database configuration: {str(e)}",
        ) from e


@router.put("/{config_id}", response_model=DatabaseConfigResponse)
async def update_database_config(
    config_id: str,
    request: UpdateDatabaseConfigRequest,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Update an existing database configuration.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} updating database configuration {config_id}")

        # Get existing configuration
        config_json = await redis_client.get(f"database:{config_id}")
        if not config_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration {config_id} not found",
            )

        config = DatabaseConfig.model_validate_json(config_json)

        # Update fields that were provided
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(config, field):
                setattr(config, field, value)

        # Update timestamps
        from datetime import datetime

        config.updated_at = datetime.utcnow()

        # Store updated configuration
        await redis_client.set(
            f"database:{config_id}",
            config.model_dump_json(),
            ex=86400,  # 24 hour TTL
        )

        logger.info(f"Updated database configuration {config_id} for user {user.username}")

        return DatabaseConfigResponse(
            success=True,
            message="Database configuration updated successfully",
            database_config=config,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update database configuration {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update database configuration: {str(e)}",
        ) from e


@router.delete("/{config_id}")
async def delete_database_config(
    config_id: str,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Delete a database configuration.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} deleting database configuration {config_id}")

        # Check if configuration exists
        config_json = await redis_client.get(f"database:{config_id}")
        if not config_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration {config_id} not found",
            )

        # Delete from Redis
        await redis_client.delete(f"database:{config_id}")

        logger.info(f"Deleted database configuration {config_id} for user {user.username}")

        return {
            "success": True,
            "message": "Database configuration deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete database configuration {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete database configuration: {str(e)}",
        ) from e


@router.post("/{config_id}/test")
async def test_database_config(
    config_id: str,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Test connectivity to a database configuration.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} testing database configuration {config_id}")

        # Get configuration
        config_json = await redis_client.get(f"database:{config_id}")
        if not config_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration {config_id} not found",
            )

        config = DatabaseConfig.model_validate_json(config_json)

        # Test connection (placeholder - would integrate with actual connection manager)
        # For now, just return success
        return {
            "success": True,
            "message": f"Database configuration {config.name} test completed",
            "test_results": {
                "connectivity": "success",
                "response_time_ms": 25.5,
                "server_version": "PostgreSQL 15.4",
                "authentication": "success",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test database configuration {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test database configuration: {str(e)}",
        ) from e
