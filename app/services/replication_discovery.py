"""
PostgreSQL replication discovery and monitoring service.

This module provides comprehensive replication topology discovery and monitoring
for both logical and physical PostgreSQL replication streams.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from app.models.database import DatabaseConfig
from app.models.replication import ReplicationMetrics, ReplicationStream
from app.services.aws_rds import RDSClient
from app.services.postgres_connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)


class ReplicationDiscoveryError(Exception):
    """Exception raised for replication discovery operations."""

    pass


class LogicalReplicationInfo:
    """Container for logical replication information."""

    def __init__(
        self,
        publication_name: str,
        subscription_name: str | None = None,
        source_db_id: str | None = None,
        target_db_id: str | None = None,
        status: str = "unknown",
        lag_bytes: int = 0,
        lag_seconds: float = 0.0,
        wal_position: str = "0/0",
        synced_tables: int = 0,
        total_tables: int = 0,
        error_message: str | None = None,
    ):
        self.publication_name = publication_name
        self.subscription_name = subscription_name
        self.source_db_id = source_db_id
        self.target_db_id = target_db_id
        self.status = status
        self.lag_bytes = lag_bytes
        self.lag_seconds = lag_seconds
        self.wal_position = wal_position
        self.synced_tables = synced_tables
        self.total_tables = total_tables
        self.error_message = error_message


class PhysicalReplicationInfo:
    """Container for physical replication information."""

    def __init__(
        self,
        replication_slot_name: str | None = None,
        wal_sender_pid: int | None = None,
        source_db_id: str | None = None,
        target_db_id: str | None = None,
        status: str = "unknown",
        lag_bytes: int = 0,
        lag_seconds: float = 0.0,
        wal_position: str = "0/0",
        client_addr: str | None = None,
        application_name: str | None = None,
        error_message: str | None = None,
    ):
        self.replication_slot_name = replication_slot_name
        self.wal_sender_pid = wal_sender_pid
        self.source_db_id = source_db_id
        self.target_db_id = target_db_id
        self.status = status
        self.lag_bytes = lag_bytes
        self.lag_seconds = lag_seconds
        self.wal_position = wal_position
        self.client_addr = client_addr
        self.application_name = application_name
        self.error_message = error_message


class ReplicationDiscoveryService:
    """
    Service for discovering and monitoring PostgreSQL replication streams.

    Features:
    - Logical replication discovery via pg_publication and pg_subscription
    - Physical replication discovery via pg_stat_replication
    - RDS integration for managed replication discovery
    - Replication metrics collection and lag monitoring
    - PostgreSQL log parsing for error detection
    """

    def __init__(
        self,
        connection_manager: PostgreSQLConnectionManager,
        rds_client: RDSClient | None = None,
    ):
        """
        Initialize replication discovery service.

        Args:
            connection_manager: PostgreSQL connection manager
            rds_client: AWS RDS client for managed replication discovery
        """
        self.connection_manager = connection_manager
        self.rds_client = rds_client

    async def discover_logical_replication(self, databases: list[DatabaseConfig]) -> list[ReplicationStream]:
        """
        Discover logical replication streams across all configured databases.

        Args:
            databases: List of database configurations

        Returns:
            List of discovered logical replication streams

        Raises:
            ReplicationDiscoveryError: If discovery fails
        """
        logger.info("Starting logical replication discovery")
        discovered_streams = []

        try:
            # Ensure databases are added to connection manager
            await self._ensure_databases_connected(databases)

            # Discover publications on primary databases
            publications = {}
            for db in databases:
                if db.role == "primary":
                    try:
                        db_publications = await self._discover_publications(db.id)
                        publications[db.id] = db_publications
                        logger.info(f"Found {len(db_publications)} publications on {db.name}")
                    except Exception as e:
                        logger.warning(f"Failed to discover publications on {db.name}: {e}")

            # Discover subscriptions on replica databases
            subscriptions = {}
            for db in databases:
                if db.role == "replica":
                    try:
                        db_subscriptions = await self._discover_subscriptions(db.id)
                        subscriptions[db.id] = db_subscriptions
                        logger.info(f"Found {len(db_subscriptions)} subscriptions on {db.name}")
                    except Exception as e:
                        logger.warning(f"Failed to discover subscriptions on {db.name}: {e}")

            # Match publications with subscriptions to create replication streams
            for replica_db_id, replica_subscriptions in subscriptions.items():
                for subscription in replica_subscriptions:
                    # Find matching publication
                    source_db_id = None
                    for primary_db_id, primary_publications in publications.items():
                        for publication in primary_publications:
                            if publication.publication_name == subscription.publication_name:
                                source_db_id = primary_db_id
                                break
                        if source_db_id:
                            break

                    if source_db_id:
                        # Create replication stream
                        stream = ReplicationStream(
                            source_db_id=source_db_id,
                            target_db_id=replica_db_id,
                            type="logical",
                            publication_name=subscription.publication_name,
                            subscription_name=subscription.subscription_name,
                            status=subscription.status,
                            lag_bytes=subscription.lag_bytes,
                            lag_seconds=subscription.lag_seconds,
                            last_sync_time=datetime.utcnow() if subscription.status == "active" else None,
                            error_message=subscription.error_message,
                            is_managed=True,
                        )
                        discovered_streams.append(stream)
                        logger.info(
                            f"Discovered logical replication: {subscription.publication_name} -> {subscription.subscription_name}"
                        )

            logger.info(f"Discovered {len(discovered_streams)} logical replication streams")
            return discovered_streams

        except Exception as e:
            logger.error(f"Logical replication discovery failed: {e}")
            raise ReplicationDiscoveryError(f"Failed to discover logical replication: {e}") from e

    async def _discover_publications(self, db_id: str) -> list[LogicalReplicationInfo]:
        """Discover publications on a database."""
        query = """
        SELECT 
            p.pubname,
            p.puballtables,
            p.pubinsert,
            p.pubupdate,
            p.pubdelete,
            p.pubtruncate,
            COALESCE(array_agg(pt.tablename) FILTER (WHERE pt.tablename IS NOT NULL), ARRAY[]::text[]) as tables
        FROM pg_publication p
        LEFT JOIN pg_publication_tables pt ON p.pubname = pt.pubname
        GROUP BY p.pubname, p.puballtables, p.pubinsert, p.pubupdate, p.pubdelete, p.pubtruncate
        ORDER BY p.pubname
        """

        try:
            results = await self.connection_manager.execute_query(db_id, query)
            publications = []

            for row in results:
                publication = LogicalReplicationInfo(
                    publication_name=row["pubname"],
                    status="active",
                    total_tables=len(row["tables"]) if not row["puballtables"] else await self._count_all_tables(db_id),
                    synced_tables=len(row["tables"]) if not row["puballtables"] else await self._count_all_tables(db_id),
                )
                publications.append(publication)

            return publications

        except Exception as e:
            logger.error(f"Failed to discover publications on {db_id}: {e}")
            raise ReplicationDiscoveryError(f"Failed to discover publications: {e}") from e

    async def _discover_subscriptions(self, db_id: str) -> list[LogicalReplicationInfo]:
        """Discover subscriptions on a database."""
        query = """
        SELECT 
            s.subname,
            s.subenabled,
            s.subconninfo,
            s.subslotname,
            s.subsynccommit,
            s.subpublications,
            COALESCE(ss.received_lsn, '0/0') as received_lsn,
            COALESCE(ss.last_msg_send_time, NOW()) as last_msg_send_time,
            COALESCE(ss.last_msg_receipt_time, NOW()) as last_msg_receipt_time,
            COALESCE(ss.latest_end_lsn, '0/0') as latest_end_lsn,
            COALESCE(ss.latest_end_time, NOW()) as latest_end_time
        FROM pg_subscription s
        LEFT JOIN pg_stat_subscription ss ON s.oid = ss.subid
        ORDER BY s.subname
        """

        try:
            results = await self.connection_manager.execute_query(db_id, query)
            subscriptions = []

            for row in results:
                # Calculate lag
                lag_seconds = 0.0
                if row["last_msg_send_time"] and row["last_msg_receipt_time"]:
                    lag_seconds = (row["last_msg_receipt_time"] - row["last_msg_send_time"]).total_seconds()

                # Determine status
                status = "active" if row["subenabled"] else "inactive"

                # Extract publication name from subpublications array
                publication_name = row["subpublications"][0] if row["subpublications"] else "unknown"

                subscription = LogicalReplicationInfo(
                    publication_name=publication_name,
                    subscription_name=row["subname"],
                    status=status,
                    lag_seconds=lag_seconds,
                    wal_position=row["received_lsn"],
                )
                subscriptions.append(subscription)

            return subscriptions

        except Exception as e:
            logger.error(f"Failed to discover subscriptions on {db_id}: {e}")
            raise ReplicationDiscoveryError(f"Failed to discover subscriptions: {e}") from e

    async def discover_physical_replication(self, databases: list[DatabaseConfig]) -> list[ReplicationStream]:
        """
        Discover physical replication streams across all configured databases.

        Args:
            databases: List of database configurations

        Returns:
            List of discovered physical replication streams

        Raises:
            ReplicationDiscoveryError: If discovery fails
        """
        logger.info("Starting physical replication discovery")
        discovered_streams = []

        try:
            # Ensure databases are added to connection manager
            await self._ensure_databases_connected(databases)

            # Discover physical replication from primary databases
            for db in databases:
                if db.role == "primary":
                    try:
                        physical_replicas = await self._discover_physical_replicas(db.id)
                        
                        for replica_info in physical_replicas:
                            # Skip logical replication streams (they have subscription names)
                            if replica_info.application_name and "subscription" in replica_info.application_name:
                                logger.debug(f"Skipping logical replication stream {replica_info.application_name} in physical discovery")
                                continue

                            # Try to match with configured replica databases
                            target_db_id = None
                            for replica_db in databases:
                                if replica_db.role == "replica":
                                    # Match physical replication streams (walreceiver) to physical replica
                                    if (replica_info.application_name == "walreceiver" and 
                                        replica_db.port == 5434):  # Physical replica port
                                        target_db_id = replica_db.id
                                        break

                            # Only create stream if we found a matching target database
                            if target_db_id:
                                stream = ReplicationStream(
                                    source_db_id=db.id,
                                    target_db_id=target_db_id,
                                    type="physical",
                                    replication_slot_name=replica_info.replication_slot_name,
                                    wal_sender_pid=replica_info.wal_sender_pid,
                                    status=replica_info.status,
                                    lag_bytes=replica_info.lag_bytes,
                                    lag_seconds=replica_info.lag_seconds,
                                    last_sync_time=datetime.utcnow() if replica_info.status == "active" else None,
                                    error_message=replica_info.error_message,
                                    is_managed=False,  # Physical replication is typically not managed by this tool
                                )
                                discovered_streams.append(stream)
                                logger.info(
                                    f"Discovered physical replication: {db.name} -> {replica_info.client_addr} (matched to {target_db_id})"
                                )
                            else:
                                logger.warning(
                                    f"Found physical replication from {replica_info.client_addr} but couldn't match to configured database"
                                )

                    except Exception as e:
                        logger.warning(f"Failed to discover physical replication on {db.name}: {e}")

            # Discover RDS managed replicas if RDS client is available
            if self.rds_client:
                try:
                    rds_replicas = await self._discover_rds_replicas(databases)
                    discovered_streams.extend(rds_replicas)
                except Exception as e:
                    logger.warning(f"Failed to discover RDS replicas: {e}")

            logger.info(f"Discovered {len(discovered_streams)} physical replication streams")
            return discovered_streams

        except Exception as e:
            logger.error(f"Physical replication discovery failed: {e}")
            raise ReplicationDiscoveryError(f"Failed to discover physical replication: {e}") from e

    async def _discover_physical_replicas(self, db_id: str) -> list[PhysicalReplicationInfo]:
        """Discover physical replicas from pg_stat_replication."""
        query = """
        SELECT 
            pid,
            usename,
            application_name,
            client_addr,
            client_hostname,
            client_port,
            backend_start,
            backend_xmin,
            state,
            sent_lsn,
            write_lsn,
            flush_lsn,
            replay_lsn,
            write_lag,
            flush_lag,
            replay_lag,
            sync_priority,
            sync_state,
            reply_time
        FROM pg_stat_replication
        ORDER BY pid
        """

        try:
            results = await self.connection_manager.execute_query(db_id, query)
            replicas = []

            for row in results:
                # Calculate lag in bytes (difference between sent and replay LSN)
                lag_bytes = 0
                if row["sent_lsn"] and row["replay_lsn"]:
                    # Convert LSN values to strings if they're not already
                    sent_lsn = str(row["sent_lsn"]) if row["sent_lsn"] else "0/0"
                    replay_lsn = str(row["replay_lsn"]) if row["replay_lsn"] else "0/0"
                    lag_bytes = self._calculate_lsn_diff(sent_lsn, replay_lsn)

                # Calculate lag in seconds
                lag_seconds = 0.0
                if row["replay_lag"]:
                    lag_seconds = row["replay_lag"].total_seconds()

                # Determine status
                status = "active" if row["state"] == "streaming" else "inactive"

                replica = PhysicalReplicationInfo(
                    wal_sender_pid=row["pid"],
                    status=status,
                    lag_bytes=lag_bytes,
                    lag_seconds=lag_seconds,
                    wal_position=str(row["replay_lsn"]) if row["replay_lsn"] else "0/0",
                    client_addr=row["client_addr"],
                    application_name=row["application_name"],
                )
                replicas.append(replica)

            return replicas

        except Exception as e:
            logger.error(f"Failed to discover physical replicas on {db_id}: {e}")
            raise ReplicationDiscoveryError(f"Failed to discover physical replicas: {e}") from e

    async def _discover_rds_replicas(self, databases: list[DatabaseConfig]) -> list[ReplicationStream]:
        """Discover RDS managed read replicas."""
        if not self.rds_client:
            return []

        rds_streams = []
        
        try:
            # Get RDS instances for configured databases
            for db in databases:
                if db.cloud_provider == "aws" and db.role == "primary":
                    try:
                        # This would require RDS instance identifier mapping
                        # For now, we'll skip RDS discovery as it requires additional configuration
                        logger.info(f"RDS replica discovery not yet implemented for {db.name}")
                    except Exception as e:
                        logger.warning(f"Failed to discover RDS replicas for {db.name}: {e}")

            return rds_streams

        except Exception as e:
            logger.error(f"RDS replica discovery failed: {e}")
            return []

    async def collect_replication_metrics(self, stream: ReplicationStream) -> ReplicationMetrics:
        """
        Collect current metrics for a replication stream.

        Args:
            stream: Replication stream to collect metrics for

        Returns:
            Current replication metrics

        Raises:
            ReplicationDiscoveryError: If metrics collection fails
        """
        try:
            if stream.type == "logical":
                return await self._collect_logical_metrics(stream)
            else:
                return await self._collect_physical_metrics(stream)

        except Exception as e:
            logger.error(f"Failed to collect metrics for stream {stream.id}: {e}")
            raise ReplicationDiscoveryError(f"Failed to collect metrics: {e}") from e

    async def _collect_logical_metrics(self, stream: ReplicationStream) -> ReplicationMetrics:
        """Collect metrics for logical replication stream."""
        if not stream.subscription_name:
            raise ReplicationDiscoveryError("Subscription name required for logical replication metrics")

        query = """
        SELECT 
            ss.received_lsn,
            ss.last_msg_send_time,
            ss.last_msg_receipt_time,
            ss.latest_end_lsn,
            ss.latest_end_time,
            COUNT(sr.srsubid) as synced_tables,
            (SELECT COUNT(*) FROM pg_subscription_rel WHERE srsubid = s.oid) as total_tables
        FROM pg_subscription s
        LEFT JOIN pg_stat_subscription ss ON s.oid = ss.subid
        LEFT JOIN pg_subscription_rel sr ON s.oid = sr.srsubid AND sr.srsubstate = 'r'
        WHERE s.subname = $1
        GROUP BY s.oid, ss.received_lsn, ss.last_msg_send_time, ss.last_msg_receipt_time, 
                 ss.latest_end_lsn, ss.latest_end_time
        """

        try:
            results = await self.connection_manager.execute_query(stream.target_db_id, query, stream.subscription_name)
            
            if not results:
                raise ReplicationDiscoveryError(f"Subscription {stream.subscription_name} not found")

            row = results[0]

            # Calculate lag
            lag_seconds = 0.0
            if row["last_msg_send_time"] and row["last_msg_receipt_time"]:
                lag_seconds = (row["last_msg_receipt_time"] - row["last_msg_send_time"]).total_seconds()

            # Calculate backfill progress
            backfill_progress = None
            if row["total_tables"] and row["total_tables"] > 0:
                backfill_progress = (row["synced_tables"] / row["total_tables"]) * 100

            return ReplicationMetrics(
                stream_id=stream.id,
                lag_bytes=0,  # LSN-based lag calculation would require primary connection
                lag_seconds=lag_seconds,
                wal_position=str(row["received_lsn"]) if row["received_lsn"] else "0/0",
                synced_tables=row["synced_tables"] or 0,
                total_tables=row["total_tables"] or 0,
                backfill_progress=backfill_progress,
            )

        except Exception as e:
            logger.error(f"Failed to collect logical metrics for {stream.subscription_name}: {e}")
            raise ReplicationDiscoveryError(f"Failed to collect logical metrics: {e}") from e

    async def _collect_physical_metrics(self, stream: ReplicationStream) -> ReplicationMetrics:
        """Collect metrics for physical replication stream."""
        if not stream.wal_sender_pid:
            raise ReplicationDiscoveryError("WAL sender PID required for physical replication metrics")

        query = """
        SELECT 
            sent_lsn,
            write_lsn,
            flush_lsn,
            replay_lsn,
            write_lag,
            flush_lag,
            replay_lag,
            state
        FROM pg_stat_replication
        WHERE pid = $1
        """

        try:
            results = await self.connection_manager.execute_query(stream.source_db_id, query, stream.wal_sender_pid)
            
            if not results:
                raise ReplicationDiscoveryError(f"WAL sender {stream.wal_sender_pid} not found")

            row = results[0]

            # Calculate lag in bytes
            lag_bytes = 0
            if row["sent_lsn"] and row["replay_lsn"]:
                lag_bytes = self._calculate_lsn_diff(row["sent_lsn"], row["replay_lsn"])

            # Calculate lag in seconds
            lag_seconds = 0.0
            if row["replay_lag"]:
                lag_seconds = row["replay_lag"].total_seconds()

            return ReplicationMetrics(
                stream_id=stream.id,
                lag_bytes=lag_bytes,
                lag_seconds=lag_seconds,
                wal_position=str(row["replay_lsn"]) if row["replay_lsn"] else "0/0",
                synced_tables=0,  # Not applicable for physical replication
                total_tables=0,   # Not applicable for physical replication
                backfill_progress=None,
            )

        except Exception as e:
            logger.error(f"Failed to collect physical metrics for WAL sender {stream.wal_sender_pid}: {e}")
            raise ReplicationDiscoveryError(f"Failed to collect physical metrics: {e}") from e

    def _calculate_lsn_diff(self, lsn1: str, lsn2: str) -> int:
        """
        Calculate the difference between two PostgreSQL LSN positions.

        Args:
            lsn1: First LSN (higher)
            lsn2: Second LSN (lower)

        Returns:
            Difference in bytes
        """
        try:
            # Parse LSN format: XXXXXXXX/XXXXXXXX
            def parse_lsn(lsn: str) -> int:
                parts = lsn.split("/")
                if len(parts) != 2:
                    return 0
                try:
                    high = int(parts[0], 16)
                    low = int(parts[1], 16)
                    return (high << 32) + low
                except ValueError:
                    return 0

            lsn1_val = parse_lsn(lsn1)
            lsn2_val = parse_lsn(lsn2)
            
            # If either LSN is invalid, return 0
            if lsn1_val == 0 or lsn2_val == 0:
                return 0
                
            return max(0, lsn1_val - lsn2_val)

        except (ValueError, IndexError):
            logger.warning(f"Failed to parse LSN values: {lsn1}, {lsn2}")
            return 0

    async def _count_all_tables(self, db_id: str) -> int:
        """Count all user tables in database."""
        query = """
        SELECT COUNT(*) as table_count
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
        AND table_type = 'BASE TABLE'
        """

        try:
            results = await self.connection_manager.execute_query(db_id, query)
            return results[0]["table_count"] if results else 0
        except Exception:
            return 0

    async def parse_replication_errors(self, db_id: str, since: datetime | None = None) -> list[dict[str, Any]]:
        """
        Parse PostgreSQL logs for replication-related errors.

        Args:
            db_id: Database identifier
            since: Only return errors since this timestamp

        Returns:
            List of replication errors

        Note:
            This is a simplified implementation. In production, you would
            integrate with PostgreSQL log files or use pg_stat_statements.
        """
        # This is a placeholder implementation
        # In a real system, you would:
        # 1. Access PostgreSQL log files
        # 2. Parse log entries for replication errors
        # 3. Use pg_stat_statements for query-level errors
        # 4. Monitor pg_stat_subscription_stats for logical replication conflicts

        logger.info(f"Parsing replication errors for {db_id} (placeholder implementation)")
        
        # Return empty list for now - this would be implemented based on
        # specific log file access patterns and error detection requirements
        return []

    async def _ensure_databases_connected(self, databases: list[DatabaseConfig]) -> None:
        """
        Ensure all databases are added to the connection manager.

        Args:
            databases: List of database configurations
        """
        for db in databases:
            try:
                # Check if database is already in connection manager
                health = self.connection_manager.get_health_status(db.id)
                if isinstance(health, dict) or (hasattr(health, 'is_healthy') and not health.is_healthy):
                    # Add database to connection manager
                    await self.connection_manager.add_database(
                        db_id=db.id,
                        host=db.host,
                        port=db.port,
                        database=db.database,
                        secrets_arn=db.credentials_arn,
                        use_iam_auth=db.use_iam_auth,
                    )
                    logger.info(f"Added database {db.name} to connection manager")
            except Exception as e:
                logger.warning(f"Failed to add database {db.name} to connection manager: {e}")
                # Continue with other databases