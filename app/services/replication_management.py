"""
Replication stream management service.

This module provides functionality for creating, managing, and destroying
PostgreSQL logical replication streams.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from app.models.replication import ReplicationStream
from app.services.postgres_connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)


class ReplicationManagementError(Exception):
    """Exception raised for replication management errors."""

    pass


class ReplicationStreamManager:
    """Service for managing PostgreSQL logical replication streams."""

    def __init__(self, connection_manager: PostgreSQLConnectionManager):
        """Initialize the replication stream manager."""
        self.connection_manager = connection_manager

    async def create_logical_replication_stream(
        self,
        source_db_id: str,
        target_db_id: str,
        publication_name: str,
        subscription_name: str,
        table_names: list[str] | None = None,
        initial_sync: bool = True,
    ) -> ReplicationStream:
        """
        Create a logical replication stream between two databases.

        Args:
            source_db_id: ID of the source database
            target_db_id: ID of the target database
            publication_name: Name of the publication to create
            subscription_name: Name of the subscription to create
            table_names: List of table names to replicate (None for all tables)
            initial_sync: Whether to perform initial data sync

        Returns:
            ReplicationStream: The created replication stream

        Raises:
            ReplicationManagementError: If stream creation fails
        """
        try:
            logger.info(f"Creating logical replication stream: {publication_name} -> {subscription_name}")

            # Validate databases exist and are accessible
            await self._validate_databases(source_db_id, target_db_id)

            # Create publication on source database
            await self._create_publication(source_db_id, publication_name, table_names)

            # Create subscription on target database
            await self._create_subscription(
                target_db_id,
                subscription_name,
                publication_name,
                source_db_id,
                initial_sync,
            )

            # Create and return replication stream object
            stream = ReplicationStream(
                id=str(uuid.uuid4()),
                source_db_id=source_db_id,
                target_db_id=target_db_id,
                type="logical",
                publication_name=publication_name,
                subscription_name=subscription_name,
                status="active",
                lag_bytes=0,
                lag_seconds=0.0,
                last_sync_time=datetime.utcnow(),
                is_managed=True,
            )

            logger.info(f"Successfully created replication stream: {stream.id}")
            return stream

        except Exception as e:
            logger.error(f"Failed to create replication stream: {e}")
            raise ReplicationManagementError(f"Failed to create replication stream: {e}") from e

    async def destroy_logical_replication_stream(
        self, source_db_id: str, target_db_id: str, publication_name: str, subscription_name: str
    ) -> None:
        """
        Destroy a logical replication stream.

        Args:
            source_db_id: ID of the source database
            target_db_id: ID of the target database
            publication_name: Name of the publication to drop
            subscription_name: Name of the subscription to drop

        Raises:
            ReplicationManagementError: If stream destruction fails
        """
        try:
            logger.info(f"Destroying logical replication stream: {publication_name} -> {subscription_name}")

            # Drop subscription first (on target database)
            await self._drop_subscription(target_db_id, subscription_name)

            # Drop publication (on source database)
            await self._drop_publication(source_db_id, publication_name)

            logger.info(f"Successfully destroyed replication stream: {publication_name} -> {subscription_name}")

        except Exception as e:
            logger.error(f"Failed to destroy replication stream: {e}")
            raise ReplicationManagementError(f"Failed to destroy replication stream: {e}") from e

    async def validate_replication_stream(
        self, source_db_id: str, target_db_id: str, table_names: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Validate that a replication stream can be created between two databases.

        Args:
            source_db_id: ID of the source database
            target_db_id: ID of the target database
            table_names: List of table names to validate (None for all tables)

        Returns:
            dict: Validation results with success status and any issues

        Raises:
            ReplicationManagementError: If validation fails
        """
        try:
            logger.info(f"Validating replication stream: {source_db_id} -> {target_db_id}")

            validation_results = {
                "success": True,
                "issues": [],
                "warnings": [],
                "source_db_accessible": False,
                "target_db_accessible": False,
                "replication_user_exists": False,
                "tables_exist": False,
            }

            # Check database connectivity
            try:
                await self._validate_databases(source_db_id, target_db_id)
                validation_results["source_db_accessible"] = True
                validation_results["target_db_accessible"] = True
            except Exception as e:
                validation_results["success"] = False
                validation_results["issues"].append(f"Database connectivity issue: {e}")

            # Check replication user permissions
            try:
                await self._check_replication_permissions(source_db_id, target_db_id)
                validation_results["replication_user_exists"] = True
            except Exception as e:
                validation_results["success"] = False
                validation_results["issues"].append(f"Replication permissions issue: {e}")

            # Check table existence if specified
            if table_names:
                try:
                    missing_tables = await self._check_table_existence(source_db_id, table_names)
                    if missing_tables:
                        validation_results["success"] = False
                        validation_results["issues"].append(f"Missing tables on source database: {missing_tables}")
                    else:
                        validation_results["tables_exist"] = True
                except Exception as e:
                    validation_results["warnings"].append(f"Could not validate table existence: {e}")

            return validation_results

        except Exception as e:
            logger.error(f"Failed to validate replication stream: {e}")
            raise ReplicationManagementError(f"Failed to validate replication stream: {e}") from e

    async def _validate_databases(self, source_db_id: str, target_db_id: str) -> None:
        """Validate that both databases exist and are accessible."""
        # Check source database
        source_health = self.connection_manager.get_health_status(source_db_id)
        if not source_health.is_healthy:
            raise ReplicationManagementError(
                f"Source database {source_db_id} is not accessible: {source_health.error_message}"
            )

        # Check target database
        target_health = self.connection_manager.get_health_status(target_db_id)
        if not target_health.is_healthy:
            raise ReplicationManagementError(
                f"Target database {target_db_id} is not accessible: {target_health.error_message}"
            )

    async def _create_publication(
        self, source_db_id: str, publication_name: str, table_names: list[str] | None = None
    ) -> None:
        """Create a publication on the source database."""
        if table_names:
            # Create publication for specific tables
            table_list = ", ".join(table_names)
            query = f"CREATE PUBLICATION {publication_name} FOR TABLE {table_list}"
        else:
            # Create publication for all tables
            query = f"CREATE PUBLICATION {publication_name} FOR ALL TABLES"

        await self.connection_manager.execute_query(source_db_id, query)
        logger.info(f"Created publication {publication_name} on database {source_db_id}")

    async def _create_subscription(
        self,
        target_db_id: str,
        subscription_name: str,
        publication_name: str,
        source_db_id: str,
        initial_sync: bool = True,
    ) -> None:
        """Create a subscription on the target database."""
        # Get source database connection info
        # For now, we'll use a placeholder connection string
        # In a real implementation, this would get the actual connection details
        source_conn_string = "host=postgres-primary port=5432 dbname=testdb user=testuser password=testpass"

        copy_data = "true" if initial_sync else "false"
        query = f"""
        CREATE SUBSCRIPTION {subscription_name}
        CONNECTION '{source_conn_string}'
        PUBLICATION {publication_name}
        WITH (copy_data = {copy_data})
        """

        await self.connection_manager.execute_query(target_db_id, query)
        logger.info(f"Created subscription {subscription_name} on database {target_db_id}")

    async def _drop_subscription(self, target_db_id: str, subscription_name: str) -> None:
        """Drop a subscription from the target database."""
        query = f"DROP SUBSCRIPTION IF EXISTS {subscription_name}"
        await self.connection_manager.execute_query(target_db_id, query)
        logger.info(f"Dropped subscription {subscription_name} from database {target_db_id}")

    async def _drop_publication(self, source_db_id: str, publication_name: str) -> None:
        """Drop a publication from the source database."""
        query = f"DROP PUBLICATION IF EXISTS {publication_name}"
        await self.connection_manager.execute_query(source_db_id, query)
        logger.info(f"Dropped publication {publication_name} from database {source_db_id}")

    async def _check_replication_permissions(self, source_db_id: str, target_db_id: str) -> None:
        """Check that the user has replication permissions."""
        # Check if user has replication privileges on source
        query = """
        SELECT rolreplication
        FROM pg_roles
        WHERE rolname = current_user
        """
        result = await self.connection_manager.execute_query(source_db_id, query)
        if not result or not result[0]["rolreplication"]:
            raise ReplicationManagementError("User does not have replication privileges on source database")

    async def _check_table_existence(self, source_db_id: str, table_names: list[str]) -> list[str]:
        """Check which tables exist on the source database."""
        if not table_names:
            return []

        # Query to check table existence
        table_list = "', '".join(table_names)
        query = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN ('{table_list}')
        """

        result = await self.connection_manager.execute_query(source_db_id, query)
        existing_tables = {row["table_name"] for row in result}
        missing_tables = [table for table in table_names if table not in existing_tables]

        return missing_tables
