"""
Schema Migration Execution API

Provides endpoints for executing schema migrations across database topologies.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.dependencies import get_connection_manager, get_redis_client, get_replication_discovery_service
from app.middleware.auth import get_current_user
from app.models.auth import User
from app.services.migration_executor import MigrationExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/migrations", tags=["Schema Migrations"])


class MigrationCreateRequest(BaseModel):
    """Request model for creating a new migration"""

    filename: str
    content: str


class MigrationExecutionRequest(BaseModel):
    """Request model for executing a migration"""

    migration_id: str


class MigrationStatusResponse(BaseModel):
    """Response model for migration status"""

    success: bool
    databases: dict[str, Any]
    pending_migrations: list[dict[str, Any]]
    missing_migrations: dict[str, list[str]]


class MigrationResult(BaseModel):
    """Result of a migration execution on a single database"""

    database_id: str
    database_name: str
    success: bool
    execution_time_ms: float
    rows_affected: int | None = None
    error_message: str | None = None
    executed_statements: list[str] = []


class MigrationExecutionResponse(BaseModel):
    """Response model for migration execution"""

    execution_id: str
    success: bool
    message: str
    total_databases: int
    successful_databases: int
    failed_databases: int
    execution_time_ms: float
    results: list[MigrationResult]
    rollback_performed: bool = False


class MigrationHistoryItem(BaseModel):
    """Migration history item"""

    execution_id: str
    executed_at: datetime
    executed_by: str
    sql_script: str
    target_databases: list[str]
    success: bool
    total_databases: int
    successful_databases: int
    failed_databases: int
    execution_time_ms: float


class MigrationHistoryResponse(BaseModel):
    """Response model for migration history"""

    success: bool
    total_count: int
    migrations: list[MigrationHistoryItem]


# WebSocket connection manager for real-time migration progress
class MigrationConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_progress(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                self.disconnect(connection)


migration_manager = MigrationConnectionManager()


@router.post("/create", response_model=dict[str, Any])
async def create_migration(
    request: MigrationCreateRequest,
    user: User = Depends(get_current_user),
    connection_manager=Depends(get_connection_manager),
    discovery_service=Depends(get_replication_discovery_service),
    redis_client=Depends(get_redis_client),
):
    """
    Create a new migration and store it for execution.

    Requires authentication.
    """
    try:
        executor = MigrationExecutor(connection_manager, discovery_service, redis_client)

        migration_id = await executor.store_migration(
            filename=request.filename,
            content=request.content,
            created_by=user.username,
        )

        return {
            "success": True,
            "message": "Migration created successfully",
            "migration_id": migration_id,
        }

    except Exception as e:
        logger.error(f"Failed to create migration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create migration: {str(e)}",
        ) from e


@router.post("/execute", response_model=dict[str, Any])
async def execute_migration(
    request: MigrationExecutionRequest,
    user: User = Depends(get_current_user),
    connection_manager=Depends(get_connection_manager),
    discovery_service=Depends(get_replication_discovery_service),
    redis_client=Depends(get_redis_client),
):
    """
    Execute a migration across the replication topology.

    Requires authentication.
    """
    try:
        executor = MigrationExecutor(connection_manager, discovery_service, redis_client)

        logger.info(f"User {user.username} executing migration {request.migration_id}")

        result = await executor.execute_migration(request.migration_id)

        return {
            "success": result["success"],
            "message": f"Migration execution {'completed' if result['success'] else 'failed'}",
            "migration_id": result["migration_id"],
            "results": result["results"],
            "retry_count": result["retry_count"],
        }

    except Exception as e:
        logger.error(f"Failed to execute migration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute migration: {str(e)}",
        ) from e


@router.get("/status", response_model=MigrationStatusResponse)
async def get_migration_status(
    user: User = Depends(get_current_user),
    connection_manager=Depends(get_connection_manager),
    discovery_service=Depends(get_replication_discovery_service),
    redis_client=Depends(get_redis_client),
):
    """
    Get migration status across all databases.

    Requires authentication.
    """
    try:
        executor = MigrationExecutor(connection_manager, discovery_service, redis_client)

        # Get all configured databases
        databases = await executor._get_configured_databases()

        status = await executor.get_migration_status(databases)

        return MigrationStatusResponse(
            success=True,
            databases=status["databases"],
            pending_migrations=status["pending_migrations"],
            missing_migrations=status["missing_migrations"],
        )

    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get migration status: {str(e)}",
        ) from e


@router.post("/retry/{migration_id}", response_model=dict[str, Any])
async def retry_migration(
    migration_id: str,
    user: User = Depends(get_current_user),
    connection_manager=Depends(get_connection_manager),
    discovery_service=Depends(get_replication_discovery_service),
    redis_client=Depends(get_redis_client),
):
    """
    Retry a failed migration.

    Requires authentication.
    """
    try:
        executor = MigrationExecutor(connection_manager, discovery_service, redis_client)

        logger.info(f"User {user.username} retrying migration {migration_id}")

        result = await executor.retry_failed_migration(migration_id)

        return {
            "success": result["success"],
            "message": f"Migration retry {'completed' if result['success'] else 'failed'}",
            "migration_id": result["migration_id"],
            "results": result["results"],
            "retry_count": result["retry_count"],
        }

    except Exception as e:
        logger.error(f"Failed to retry migration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry migration: {str(e)}",
        ) from e


@router.post("/setup-tables", response_model=dict[str, Any])
async def setup_migration_tables(
    user: User = Depends(get_current_user),
    connection_manager=Depends(get_connection_manager),
    discovery_service=Depends(get_replication_discovery_service),
    redis_client=Depends(get_redis_client),
):
    """
    Set up migration tracking tables in all databases.

    Requires authentication.
    """
    try:
        executor = MigrationExecutor(connection_manager, discovery_service, redis_client)

        # Get all configured databases
        databases = await executor._get_configured_databases()

        results = await executor.create_migration_tables(databases)

        successful_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - successful_count

        return {
            "success": failed_count == 0,
            "message": f"Migration tables setup: {successful_count} successful, {failed_count} failed",
            "results": results,
            "total_databases": len(results),
        }

    except Exception as e:
        logger.error(f"Failed to setup migration tables: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup migration tables: {str(e)}",
        ) from e


@router.post("/validate", response_model=dict[str, Any])
async def validate_migration(
    request: MigrationCreateRequest,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Validate a migration script without executing it.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} validating migration script")

        # Basic SQL validation
        validation_results = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "statement_count": 0,
            "estimated_execution_time": "< 1 second",
        }

        # Validate filename format
        if not request.filename.endswith(".sql"):
            validation_results["errors"].append("Filename must end with .sql")
            validation_results["valid"] = False

        if not request.filename.replace(".sql", "").replace("_", "").replace("-", "").isalnum():
            validation_results["warnings"].append(
                "Filename should contain only alphanumeric characters, underscores, and hyphens"
            )

        # Parse SQL statements
        statements = _parse_sql_statements(request.content)
        validation_results["statement_count"] = len(statements)

        # Basic validation checks
        for i, statement in enumerate(statements):
            statement = statement.strip().upper()

            # Check for potentially dangerous operations
            if any(dangerous in statement for dangerous in ["DROP TABLE", "DROP DATABASE", "TRUNCATE"]):
                validation_results["warnings"].append(f"Statement {i + 1}: Contains potentially destructive operation")

            # Check for missing WHERE clauses in UPDATE/DELETE
            if statement.startswith(("UPDATE", "DELETE")) and "WHERE" not in statement:
                validation_results["warnings"].append(f"Statement {i + 1}: UPDATE/DELETE without WHERE clause")

        return {
            "success": True,
            "message": "Migration script validation completed",
            "validation_results": validation_results,
        }

    except Exception as e:
        logger.error(f"Failed to validate migration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate migration: {str(e)}",
        ) from e


@router.get("/history", response_model=MigrationHistoryResponse)
async def get_migration_history(
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis_client),
):
    """
    Get migration execution history.

    Requires authentication.
    """
    try:
        logger.info(f"User {user.username} retrieving migration history")

        # Get migration history from Redis
        pattern = "migration_history:*"
        keys = await redis_client.keys(pattern)

        migrations = []
        for key in keys:
            try:
                history_json = await redis_client.get(key)
                if history_json:
                    import json

                    history_data = json.loads(history_json)
                    migration = MigrationHistoryItem(**history_data)
                    migrations.append(migration)
            except Exception as e:
                logger.warning(f"Failed to parse migration history from key {key}: {e}")
                continue

        # Sort by execution time (newest first)
        migrations.sort(key=lambda x: x.executed_at, reverse=True)

        # Apply pagination
        total_count = len(migrations)
        migrations = migrations[offset : offset + limit]

        return MigrationHistoryResponse(
            success=True,
            total_count=total_count,
            migrations=migrations,
        )

    except Exception as e:
        logger.error(f"Failed to get migration history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get migration history: {str(e)}",
        ) from e


@router.websocket("/progress/{execution_id}")
async def migration_progress_websocket(websocket: WebSocket, execution_id: str):
    """
    WebSocket endpoint for real-time migration progress updates.
    """
    await migration_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        migration_manager.disconnect(websocket)


# Helper functions


async def _get_target_databases(target_db_ids: list[str] | None, redis_client) -> list[dict[str, Any]]:
    """Get target database configurations"""
    if target_db_ids is None:
        # Get all databases
        pattern = "database:*"
        keys = await redis_client.keys(pattern)
    else:
        # Get specific databases
        keys = [f"database:{db_id}" for db_id in target_db_ids]

    databases = []
    for key in keys:
        try:
            config_json = await redis_client.get(key)
            if config_json:
                import json

                config = json.loads(config_json)
                databases.append(config)
        except Exception as e:
            logger.warning(f"Failed to load database config from {key}: {e}")
            continue

    return databases


async def _execute_migration_on_database(db_config: dict[str, Any], sql_script: str, dry_run: bool) -> MigrationResult:
    """Execute migration on a single database"""
    start_time = datetime.utcnow()

    try:
        # Parse SQL statements
        statements = _parse_sql_statements(sql_script)

        if dry_run:
            # Simulate execution for dry run
            end_time = datetime.utcnow()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            return MigrationResult(
                database_id=db_config["id"],
                database_name=db_config["name"],
                success=True,
                execution_time_ms=execution_time_ms,
                rows_affected=0,
                executed_statements=statements,
            )

        # TODO: Implement actual database execution
        # For now, simulate successful execution
        import asyncio

        await asyncio.sleep(0.1)  # Simulate execution time

        end_time = datetime.utcnow()
        execution_time_ms = (end_time - start_time).total_seconds() * 1000

        return MigrationResult(
            database_id=db_config["id"],
            database_name=db_config["name"],
            success=True,
            execution_time_ms=execution_time_ms,
            rows_affected=len(statements),
            executed_statements=statements,
        )

    except Exception as e:
        end_time = datetime.utcnow()
        execution_time_ms = (end_time - start_time).total_seconds() * 1000

        return MigrationResult(
            database_id=db_config["id"],
            database_name=db_config["name"],
            success=False,
            execution_time_ms=execution_time_ms,
            error_message=str(e),
        )


def _parse_sql_statements(sql_script: str) -> list[str]:
    """Parse SQL script into individual statements"""
    # Simple statement parsing (would be enhanced with proper SQL parser)
    statements = []
    current_statement = ""

    for line in sql_script.split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue

        current_statement += line + " "

        if line.endswith(";"):
            statements.append(current_statement.strip())
            current_statement = ""

    if current_statement.strip():
        statements.append(current_statement.strip())

    return statements


async def _perform_rollback(results: list[MigrationResult], successful_count: int):
    """Perform rollback on successful migrations"""
    # TODO: Implement actual rollback logic
    logger.info(f"Performing rollback on {successful_count} successful migrations")
    pass


async def _store_migration_history(
    execution_id: str,
    executed_by: str,
    request: MigrationExecutionRequest,
    results: list[MigrationResult],
    successful_count: int,
    failed_count: int,
    execution_time_ms: float,
    redis_client,
):
    """Store migration execution history"""
    try:
        history_item = MigrationHistoryItem(
            execution_id=execution_id,
            executed_at=datetime.utcnow(),
            executed_by=executed_by,
            sql_script=request.sql_script,
            target_databases=request.target_databases or [],
            success=failed_count == 0,
            total_databases=len(results),
            successful_databases=successful_count,
            failed_databases=failed_count,
            execution_time_ms=execution_time_ms,
        )

        # Store in Redis with 30-day TTL
        await redis_client.set(
            f"migration_history:{execution_id}",
            history_item.model_dump_json(),
            ex=30 * 24 * 3600,  # 30 days
        )

    except Exception as e:
        logger.error(f"Failed to store migration history: {e}")
