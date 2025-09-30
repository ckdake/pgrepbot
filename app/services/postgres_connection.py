"""
PostgreSQL connection management service.

This module provides async PostgreSQL connection management with connection pooling,
credential resolution via Secrets Manager, IAM authentication, and health monitoring.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import asyncpg
from asyncpg import Connection, Pool

from app.services.aws_rds import RDSClient
from app.services.aws_secrets import SecretsManagerClient

logger = logging.getLogger(__name__)


class PostgreSQLConnectionError(Exception):
    """Exception raised for PostgreSQL connection operations."""

    pass


class DatabaseCredentials:
    """Database credentials container."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        use_iam_auth: bool = False,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.use_iam_auth = use_iam_auth

    def to_connection_params(self) -> dict[str, Any]:
        """Convert to asyncpg connection parameters."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.username,
            "password": self.password,
        }


class ConnectionHealth:
    """Connection health status container."""

    def __init__(
        self,
        is_healthy: bool,
        last_check: datetime,
        error_message: str | None = None,
        response_time_ms: float | None = None,
        server_version: str | None = None,
    ):
        self.is_healthy = is_healthy
        self.last_check = last_check
        self.error_message = error_message
        self.response_time_ms = response_time_ms
        self.server_version = server_version

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "is_healthy": self.is_healthy,
            "last_check": self.last_check.isoformat(),
            "error_message": self.error_message,
            "response_time_ms": self.response_time_ms,
            "server_version": self.server_version,
        }


class PostgreSQLConnectionManager:
    """
    Async PostgreSQL connection manager with connection pooling and health monitoring.

    Features:
    - Connection pooling with asyncpg
    - Credential resolution via Secrets Manager
    - IAM authentication support
    - Health monitoring with automatic reconnection
    - Connection lifecycle management
    """

    def __init__(
        self,
        secrets_client: SecretsManagerClient | None = None,
        rds_client: RDSClient | None = None,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
        pool_max_queries: int = 50000,
        pool_max_inactive_connection_lifetime: float = 300.0,
        health_check_interval: int = 30,
    ):
        """
        Initialize PostgreSQL connection manager.

        Args:
            secrets_client: AWS Secrets Manager client for credential resolution
            rds_client: AWS RDS client for IAM token generation
            pool_min_size: Minimum connections in pool
            pool_max_size: Maximum connections in pool
            pool_max_queries: Max queries per connection before recycling
            pool_max_inactive_connection_lifetime: Max inactive time before closing
            health_check_interval: Health check interval in seconds
        """
        self.secrets_client = secrets_client
        self.rds_client = rds_client
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.pool_max_queries = pool_max_queries
        self.pool_max_inactive_connection_lifetime = pool_max_inactive_connection_lifetime
        self.health_check_interval = health_check_interval

        # Connection pools by database identifier
        self._pools: dict[str, Pool] = {}
        self._credentials: dict[str, DatabaseCredentials] = {}
        self._health_status: dict[str, ConnectionHealth] = {}
        self._health_check_tasks: dict[str, asyncio.Task] = {}

    async def add_database(
        self,
        db_id: str,
        host: str,
        port: int,
        database: str,
        username: str | None = None,
        password: str | None = None,
        secrets_arn: str | None = None,
        use_iam_auth: bool = False,
    ) -> None:
        """
        Add a database connection to the manager.

        Args:
            db_id: Unique database identifier
            host: Database host
            port: Database port
            database: Database name
            username: Database username (if not using secrets)
            password: Database password (if not using secrets)
            secrets_arn: AWS Secrets Manager ARN for credentials
            use_iam_auth: Whether to use IAM authentication

        Raises:
            PostgreSQLConnectionError: If credential resolution or connection fails
        """
        try:
            # Resolve credentials
            if secrets_arn and self.secrets_client:
                logger.info(f"Resolving credentials for {db_id} from Secrets Manager")
                credentials = await self._resolve_credentials_from_secrets(secrets_arn, use_iam_auth)
            elif username and password:
                logger.info(f"Using provided credentials for {db_id}")
                credentials = DatabaseCredentials(
                    host=host,
                    port=port,
                    database=database,
                    username=username,
                    password=password,
                    use_iam_auth=use_iam_auth,
                )
            else:
                raise PostgreSQLConnectionError(
                    f"No credentials provided for database {db_id}. Provide either secrets_arn or username/password."
                )

            # Store credentials
            self._credentials[db_id] = credentials

            # Create connection pool
            await self._create_pool(db_id, credentials)

            # Start health monitoring
            await self._start_health_monitoring(db_id)

            logger.info(f"Successfully added database {db_id}")

        except Exception as e:
            logger.error(f"Failed to add database {db_id}: {e}")
            raise PostgreSQLConnectionError(f"Failed to add database {db_id}: {e}") from e

    async def _resolve_credentials_from_secrets(self, secrets_arn: str, use_iam_auth: bool) -> DatabaseCredentials:
        """Resolve database credentials from AWS Secrets Manager."""
        if not self.secrets_client:
            raise PostgreSQLConnectionError("Secrets Manager client not configured")

        try:
            credentials_data = await self.secrets_client.get_database_credentials(secrets_arn)

            # If using IAM auth, generate token instead of using stored password
            password = credentials_data["password"]
            if use_iam_auth and self.rds_client:
                logger.info("Generating IAM authentication token")
                password = await self.rds_client.generate_auth_token(
                    db_hostname=credentials_data["host"],
                    port=credentials_data["port"],
                    db_username=credentials_data["username"],
                )

            return DatabaseCredentials(
                host=credentials_data["host"],
                port=credentials_data["port"],
                database=credentials_data["dbname"],
                username=credentials_data["username"],
                password=password,
                use_iam_auth=use_iam_auth,
            )

        except Exception as e:
            raise PostgreSQLConnectionError(f"Failed to resolve credentials: {e}") from e

    async def _create_pool(self, db_id: str, credentials: DatabaseCredentials) -> None:
        """Create connection pool for database."""
        try:
            logger.info(f"Creating connection pool for {db_id}")

            connection_params = credentials.to_connection_params()

            # Add SSL configuration for IAM auth
            if credentials.use_iam_auth:
                connection_params["ssl"] = "require"

            pool = await asyncpg.create_pool(
                **connection_params,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
                max_queries=self.pool_max_queries,
                max_inactive_connection_lifetime=self.pool_max_inactive_connection_lifetime,
                command_timeout=10,
            )

            self._pools[db_id] = pool
            logger.info(f"Connection pool created for {db_id}")

        except Exception as e:
            raise PostgreSQLConnectionError(f"Failed to create pool for {db_id}: {e}") from e

    async def _start_health_monitoring(self, db_id: str) -> None:
        """Start health monitoring task for database."""
        if db_id in self._health_check_tasks:
            # Cancel existing task
            self._health_check_tasks[db_id].cancel()

        # Start new health check task
        task = asyncio.create_task(self._health_check_loop(db_id))
        self._health_check_tasks[db_id] = task
        logger.info(f"Started health monitoring for {db_id}")

    async def _health_check_loop(self, db_id: str) -> None:
        """Health check loop for a database."""
        while True:
            try:
                await self._perform_health_check(db_id)
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                logger.info(f"Health check cancelled for {db_id}")
                break
            except Exception as e:
                logger.error(f"Health check error for {db_id}: {e}")
                await asyncio.sleep(self.health_check_interval)

    async def _perform_health_check(self, db_id: str) -> None:
        """Perform health check for a database."""
        if db_id not in self._pools:
            return

        pool = self._pools[db_id]
        start_time = datetime.now()

        try:
            async with pool.acquire() as conn:
                # Simple health check query
                result = await conn.fetchval("SELECT 1")
                version = await conn.fetchval("SELECT version()")

                if result == 1:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    self._health_status[db_id] = ConnectionHealth(
                        is_healthy=True,
                        last_check=datetime.now(),
                        response_time_ms=response_time,
                        server_version=version.split()[1] if version else None,
                    )
                else:
                    self._health_status[db_id] = ConnectionHealth(
                        is_healthy=False,
                        last_check=datetime.now(),
                        error_message="Health check query returned unexpected result",
                    )

        except Exception as e:
            logger.warning(f"Health check failed for {db_id}: {e}")
            self._health_status[db_id] = ConnectionHealth(
                is_healthy=False,
                last_check=datetime.now(),
                error_message=str(e),
            )

            # Attempt to recreate pool if connection is completely broken
            if "connection" in str(e).lower() or "closed" in str(e).lower():
                logger.info(f"Attempting to recreate pool for {db_id}")
                try:
                    await self._recreate_pool(db_id)
                except Exception as recreate_error:
                    logger.error(f"Failed to recreate pool for {db_id}: {recreate_error}")

    async def _recreate_pool(self, db_id: str) -> None:
        """Recreate connection pool for database."""
        if db_id not in self._credentials:
            return

        # Close existing pool
        if db_id in self._pools:
            await self._pools[db_id].close()
            del self._pools[db_id]

        # Recreate pool
        credentials = self._credentials[db_id]

        # Refresh IAM token if using IAM auth
        if credentials.use_iam_auth and self.rds_client:
            logger.info(f"Refreshing IAM token for {db_id}")
            new_password = await self.rds_client.generate_auth_token(
                db_hostname=credentials.host,
                port=credentials.port,
                db_username=credentials.username,
            )
            credentials.password = new_password

        await self._create_pool(db_id, credentials)

    async def get_connection(self, db_id: str) -> Connection:
        """
        Get a connection from the pool.

        Args:
            db_id: Database identifier

        Returns:
            AsyncPG connection

        Raises:
            PostgreSQLConnectionError: If database not found or connection fails
        """
        if db_id not in self._pools:
            raise PostgreSQLConnectionError(f"Database {db_id} not found")

        try:
            pool = self._pools[db_id]
            return await pool.acquire()
        except Exception as e:
            logger.error(f"Failed to acquire connection for {db_id}: {e}")
            raise PostgreSQLConnectionError(f"Failed to get connection for {db_id}: {e}") from e

    async def execute_query(self, db_id: str, query: str, *args, timeout: float | None = None) -> Any:
        """
        Execute a query on the specified database.

        Args:
            db_id: Database identifier
            query: SQL query to execute
            args: Query parameters
            timeout: Query timeout in seconds

        Returns:
            Query result

        Raises:
            PostgreSQLConnectionError: If execution fails
        """
        if db_id not in self._pools:
            raise PostgreSQLConnectionError(f"Database {db_id} not found")

        try:
            pool = self._pools[db_id]
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args, timeout=timeout)
        except Exception as e:
            logger.error(f"Query execution failed for {db_id}: {e}")
            raise PostgreSQLConnectionError(f"Query execution failed: {e}") from e

    def get_health_status(self, db_id: str | None = None) -> ConnectionHealth | dict[str, ConnectionHealth]:
        """
        Get health status for database(s).

        Args:
            db_id: Specific database ID, or None for all databases

        Returns:
            Health status for specified database or all databases
        """
        if db_id:
            return self._health_status.get(
                db_id,
                ConnectionHealth(
                    is_healthy=False,
                    last_check=datetime.now(),
                    error_message="Database not found",
                ),
            )
        return self._health_status.copy()

    def get_pool_stats(self, db_id: str | None = None) -> dict[str, dict[str, Any]]:
        """
        Get connection pool statistics.

        Args:
            db_id: Specific database ID, or None for all databases

        Returns:
            Pool statistics
        """
        stats = {}

        pools_to_check = {db_id: self._pools[db_id]} if db_id and db_id in self._pools else self._pools

        for pool_id, pool in pools_to_check.items():
            stats[pool_id] = {
                "size": pool.get_size(),
                "min_size": pool.get_min_size(),
                "max_size": pool.get_max_size(),
                "idle_size": pool.get_idle_size(),
            }

        return stats

    async def remove_database(self, db_id: str) -> None:
        """
        Remove database from manager.

        Args:
            db_id: Database identifier
        """
        logger.info(f"Removing database {db_id}")

        # Cancel health check task
        if db_id in self._health_check_tasks:
            self._health_check_tasks[db_id].cancel()
            del self._health_check_tasks[db_id]

        # Close connection pool
        if db_id in self._pools:
            await self._pools[db_id].close()
            del self._pools[db_id]

        # Clean up stored data
        self._credentials.pop(db_id, None)
        self._health_status.pop(db_id, None)

        logger.info(f"Database {db_id} removed")

    async def close_all(self) -> None:
        """Close all connections and cleanup resources."""
        logger.info("Closing all database connections")

        # Cancel all health check tasks
        for task in self._health_check_tasks.values():
            task.cancel()

        # Wait for tasks to complete
        if self._health_check_tasks:
            await asyncio.gather(*self._health_check_tasks.values(), return_exceptions=True)

        # Close all pools
        for pool in self._pools.values():
            await pool.close()

        # Clear all data
        self._pools.clear()
        self._credentials.clear()
        self._health_status.clear()
        self._health_check_tasks.clear()

        logger.info("All database connections closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_all()
