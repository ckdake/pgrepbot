"""
Schema Migration Execution Service

Handles migration execution across replication topology with proper ordering
and tracking in both Redis and PostgreSQL migration tables.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from app.models.database import DatabaseConfig
from app.services.postgres_connection import PostgreSQLConnectionManager
from app.services.replication_discovery import ReplicationDiscoveryService
from app.utils.redis_serializer import RedisModelMixin

logger = logging.getLogger(__name__)


class MigrationRecord(RedisModelMixin):
    """Migration record stored in Redis for tracking"""

    def __init__(
        self,
        migration_id: str,
        filename: str,
        content: str,
        created_at: datetime,
        created_by: str,
        status: str = "pending",
    ):
        self.migration_id = migration_id
        self.filename = filename
        self.content = content
        self.created_at = created_at
        self.created_by = created_by
        self.status = status  # pending, running, completed, failed
        self.execution_log: list[dict[str, Any]] = []
        self.retry_count = 0


class MigrationExecutionResult:
    """Result of migration execution on a database"""

    def __init__(
        self,
        database_id: str,
        database_name: str,
        success: bool,
        execution_time: float,
        error_message: str | None = None,
        rows_affected: int | None = None,
    ):
        self.database_id = database_id
        self.database_name = database_name
        self.success = success
        self.execution_time = execution_time
        self.error_message = error_message
        self.rows_affected = rows_affected


class MigrationExecutor:
    """Executes migrations across replication topology"""

    def __init__(
        self,
        connection_manager: PostgreSQLConnectionManager,
        discovery_service: ReplicationDiscoveryService,
        redis_client,
    ):
        self.connection_manager = connection_manager
        self.discovery_service = discovery_service
        self.redis_client = redis_client

    async def create_migration_tables(self, databases: list[DatabaseConfig]) -> dict[str, bool]:
        """Create migration tracking tables in all databases"""
        results = {}

        for db in databases:
            try:
                # Determine table name based on database role
                table_name = await self._get_migration_table_name(db.id)

                # Create migration table
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    content TEXT NOT NULL,
                    execution_time_ms INTEGER,
                    created_by VARCHAR(255),
                    CONSTRAINT {table_name}_id_format CHECK (
                        id ~ '^[0-9]+_[a-z0-9_]+\\.sql$'
                    )
                );

                CREATE INDEX IF NOT EXISTS {table_name}_applied_at_idx ON {table_name} (applied_at);
                CREATE INDEX IF NOT EXISTS {table_name}_created_by_idx ON {table_name} (created_by);
                """

                await self.connection_manager.execute_query(db.id, create_table_sql)
                results[db.id] = True
                logger.info(f"Created migration table {table_name} in database {db.name}")

            except Exception as e:
                logger.error(f"Failed to create migration table in {db.name}: {e}")
                results[db.id] = False

        return results

    async def store_migration(self, filename: str, content: str, created_by: str) -> str:
        """Store a new migration in Redis for tracking"""
        # Generate migration ID with timestamp prefix
        timestamp = int(time.time())
        migration_id = f"{timestamp}_{filename}"

        # Validate filename format
        if not filename.endswith(".sql"):
            raise ValueError("Migration filename must end with .sql")

        # Create migration record
        migration = MigrationRecord(
            migration_id=migration_id,
            filename=filename,
            content=content,
            created_at=datetime.utcnow(),
            created_by=created_by,
        )

        # Store in Redis
        await migration.save_to_redis(self.redis_client, f"migration:{migration_id}")

        # Add to pending migrations list
        await self.redis_client.sadd("pending_migrations", migration_id)

        logger.info(f"Stored migration {migration_id} created by {created_by}")
        return migration_id

    async def execute_migration(self, migration_id: str) -> dict[str, Any]:
        """Execute a migration across the replication topology"""
        try:
            # Load migration from Redis
            migration_data = await self.redis_client.get(f"migration:{migration_id}")
            if not migration_data:
                raise ValueError(f"Migration {migration_id} not found")

            migration = MigrationRecord.from_redis_json(migration_data)
            migration.status = "running"
            migration.retry_count += 1

            # Update status in Redis
            await migration.save_to_redis(self.redis_client, f"migration:{migration_id}")

            # Discover current topology
            databases = await self._get_configured_databases()
            topology = await self._build_execution_topology(databases)

            # Execute migration following topology order
            execution_results = []
            overall_success = True

            for level in topology:
                level_results = await self._execute_migration_level(migration, level, migration_id)
                execution_results.extend(level_results)

                # Check if any database in this level failed
                level_failed = any(not result.success for result in level_results)
                if level_failed:
                    overall_success = False
                    logger.error(f"Migration {migration_id} failed at topology level")
                    break

            # Update migration status
            migration.status = "completed" if overall_success else "failed"
            migration.execution_log.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": "execution_completed",
                    "success": overall_success,
                    "results_count": len(execution_results),
                }
            )

            await migration.save_to_redis(self.redis_client, f"migration:{migration_id}")

            # Remove from pending if successful
            if overall_success:
                await self.redis_client.srem("pending_migrations", migration_id)

            return {
                "migration_id": migration_id,
                "success": overall_success,
                "results": [
                    {
                        "database_id": r.database_id,
                        "database_name": r.database_name,
                        "success": r.success,
                        "execution_time": r.execution_time,
                        "error_message": r.error_message,
                        "rows_affected": r.rows_affected,
                    }
                    for r in execution_results
                ],
                "retry_count": migration.retry_count,
            }

        except Exception as e:
            logger.error(f"Failed to execute migration {migration_id}: {e}")
            # Update migration status to failed
            try:
                migration_data = await self.redis_client.get(f"migration:{migration_id}")
                if migration_data:
                    migration = MigrationRecord.from_redis_json(migration_data)
                    migration.status = "failed"
                    migration.execution_log.append(
                        {
                            "timestamp": datetime.utcnow().isoformat(),
                            "event": "execution_failed",
                            "error": str(e),
                        }
                    )
                    await migration.save_to_redis(self.redis_client, f"migration:{migration_id}")
            except Exception as update_error:
                logger.error(f"Failed to update migration status: {update_error}")

            raise

    async def get_migration_status(self, databases: list[DatabaseConfig]) -> dict[str, Any]:
        """Get migration status across all databases"""
        status = {
            "databases": {},
            "pending_migrations": [],
            "missing_migrations": {},
        }

        # Get pending migrations from Redis
        pending_migration_ids = await self.redis_client.smembers("pending_migrations")
        for migration_id in pending_migration_ids:
            migration_data = await self.redis_client.get(f"migration:{migration_id}")
            if migration_data:
                migration = MigrationRecord.from_redis_json(migration_data)
                status["pending_migrations"].append(
                    {
                        "migration_id": migration_id,
                        "filename": migration.filename,
                        "created_at": migration.created_at.isoformat(),
                        "created_by": migration.created_by,
                        "status": migration.status,
                        "retry_count": migration.retry_count,
                    }
                )

        # Check applied migrations in each database
        for db in databases:
            try:
                table_name = await self._get_migration_table_name(db.id)
                applied_migrations = await self.connection_manager.execute_query(
                    db.id, f"SELECT id, applied_at, created_by FROM {table_name} ORDER BY applied_at DESC"
                )

                status["databases"][db.id] = {
                    "name": db.name,
                    "migration_table": table_name,
                    "applied_migrations": [
                        {
                            "id": row["id"],
                            "applied_at": row["applied_at"].isoformat() if row["applied_at"] else None,
                            "created_by": row["created_by"],
                        }
                        for row in applied_migrations
                    ],
                    "total_applied": len(applied_migrations),
                }

                # Find missing migrations (applied in primary but not in replica)
                # applied_ids = {row["id"] for row in applied_migrations}  # TODO: implement missing migration detection
                if db.id not in status["missing_migrations"]:
                    status["missing_migrations"][db.id] = []

            except Exception as e:
                logger.error(f"Failed to get migration status for {db.name}: {e}")
                status["databases"][db.id] = {
                    "name": db.name,
                    "error": str(e),
                    "applied_migrations": [],
                    "total_applied": 0,
                }

        return status

    async def retry_failed_migration(self, migration_id: str) -> dict[str, Any]:
        """Retry a failed migration"""
        migration_data = await self.redis_client.get(f"migration:{migration_id}")
        if not migration_data:
            raise ValueError(f"Migration {migration_id} not found")

        migration = MigrationRecord.from_redis_json(migration_data)
        if migration.status not in ["failed", "pending"]:
            raise ValueError(f"Migration {migration_id} is not in a retryable state")

        # Add back to pending migrations
        await self.redis_client.sadd("pending_migrations", migration_id)

        # Execute the migration
        return await self.execute_migration(migration_id)

    async def _get_migration_table_name(self, database_id: str) -> str:
        """Get the migration table name for a database"""
        # Check if this database is a replica and get its subscription name
        try:
            # Get replication streams to find subscription name
            streams = await self.discovery_service.discover_logical_replication([])

            for stream in streams:
                if hasattr(stream, "target_database_id") and stream.target_database_id == database_id:
                    # This is a replica, use subscription-based table name
                    subscription_name = getattr(stream, "subscription_name", "replica")
                    return f"migrations_{subscription_name}"

            # Default to primary migrations table
            return "migrations"

        except Exception as e:
            logger.warning(f"Could not determine database role for {database_id}: {e}")
            return "migrations"

    async def _get_configured_databases(self) -> list[DatabaseConfig]:
        """Get all configured databases from Redis"""
        databases = []
        pattern = "database:*"
        keys = await self.redis_client.keys(pattern)

        for key in keys:
            try:
                config_json = await self.redis_client.get(key)
                if config_json:
                    import json

                    config_data = json.loads(config_json)
                    db_config = DatabaseConfig(**config_data)
                    databases.append(db_config)
            except Exception as e:
                logger.warning(f"Failed to load database config from {key}: {e}")
                continue

        return databases

    async def _build_execution_topology(self, databases: list[DatabaseConfig]) -> list[list[DatabaseConfig]]:
        """Build execution topology - primary first, then replicas by level"""
        try:
            # Discover replication topology
            logical_streams = await self.discovery_service.discover_logical_replication(databases)

            # Build topology levels
            topology = []
            db_by_id = {db.id: db for db in databases}
            processed_dbs = set()

            # Level 0: Primary databases (those that are sources but not targets)
            primary_dbs = []
            source_db_ids = set()
            target_db_ids = set()

            for stream in logical_streams:
                if hasattr(stream, "source_database_id"):
                    source_db_ids.add(stream.source_database_id)
                if hasattr(stream, "target_database_id"):
                    target_db_ids.add(stream.target_database_id)

            # Primary databases are sources but not targets
            for db_id in source_db_ids:
                if db_id not in target_db_ids and db_id in db_by_id:
                    primary_dbs.append(db_by_id[db_id])
                    processed_dbs.add(db_id)

            if primary_dbs:
                topology.append(primary_dbs)

            # Level 1+: Replica databases
            remaining_dbs = [db for db in databases if db.id not in processed_dbs]
            if remaining_dbs:
                topology.append(remaining_dbs)

            return topology

        except Exception as e:
            logger.warning(f"Failed to build execution topology: {e}")
            # Fallback: all databases in one level
            return [databases]

    async def _execute_migration_level(
        self, migration: MigrationRecord, databases: list[DatabaseConfig], migration_id: str
    ) -> list[MigrationExecutionResult]:
        """Execute migration on a level of databases"""
        tasks = []
        for db in databases:
            task = self._execute_migration_on_database(migration, db, migration_id)
            tasks.append(task)

        # Execute all databases in this level concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        execution_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                execution_results.append(
                    MigrationExecutionResult(
                        database_id=databases[i].id,
                        database_name=databases[i].name,
                        success=False,
                        execution_time=0.0,
                        error_message=str(result),
                    )
                )
            else:
                execution_results.append(result)

        return execution_results

    async def _execute_migration_on_database(
        self, migration: MigrationRecord, database: DatabaseConfig, migration_id: str
    ) -> MigrationExecutionResult:
        """Execute migration on a single database"""
        start_time = time.time()

        try:
            # Get migration table name for this database
            table_name = await self._get_migration_table_name(database.id)

            # Check if migration is already applied
            check_sql = f"SELECT COUNT(*) as count FROM {table_name} WHERE id = %s"
            result = await self.connection_manager.execute_query(database.id, check_sql, [migration_id])

            if result and result[0]["count"] > 0:
                logger.info(f"Migration {migration_id} already applied to {database.name}")
                return MigrationExecutionResult(
                    database_id=database.id,
                    database_name=database.name,
                    success=True,
                    execution_time=time.time() - start_time,
                    rows_affected=0,
                )

            # Execute the migration content
            await self.connection_manager.execute_query(database.id, migration.content)

            # Record the migration as applied
            execution_time_ms = int((time.time() - start_time) * 1000)
            record_sql = f"""
            INSERT INTO {table_name} (id, applied_at, content, execution_time_ms, created_by)
            VALUES (%s, NOW(), %s, %s, %s)
            """

            await self.connection_manager.execute_query(
                database.id,
                record_sql,
                [migration_id, migration.content, execution_time_ms, migration.created_by],
            )

            logger.info(f"Successfully applied migration {migration_id} to {database.name}")

            return MigrationExecutionResult(
                database_id=database.id,
                database_name=database.name,
                success=True,
                execution_time=time.time() - start_time,
                rows_affected=1,  # One migration record inserted
            )

        except Exception as e:
            logger.error(f"Failed to execute migration {migration_id} on {database.name}: {e}")
            return MigrationExecutionResult(
                database_id=database.id,
                database_name=database.name,
                success=False,
                execution_time=time.time() - start_time,
                error_message=str(e),
            )
