"""
AWS RDS integration service.

This module provides functionality for discovering RDS instances, clusters,
and physical replication topology using the AWS RDS API.
"""

import logging
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class RDSError(Exception):
    """Exception raised for RDS operations."""

    pass


class RDSClient:
    """
    AWS RDS client for discovering physical replication topology and instance metadata.

    Provides functionality to discover RDS instances, clusters, and their replication
    relationships for topology mapping and monitoring.
    """

    def __init__(self, region_name: str = "us-east-1", endpoint_url: str | None = None):
        """
        Initialize RDS client.

        Args:
            region_name: AWS region name
            endpoint_url: Optional endpoint URL for LocalStack testing
        """
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self._client = None

    @property
    def client(self):
        """Lazy initialization of boto3 RDS client."""
        if self._client is None:
            try:
                self._client = boto3.client(
                    "rds",
                    region_name=self.region_name,
                    endpoint_url=self.endpoint_url,
                )
            except Exception as e:
                logger.error(f"Failed to initialize RDS client: {e}")
                raise RDSError(f"Failed to initialize RDS client: {e}") from e
        return self._client

    async def list_db_instances(self) -> list[dict[str, Any]]:
        """
        List all RDS database instances in the region.

        Returns:
            List of database instance metadata dictionaries

        Raises:
            RDSError: If listing instances fails
        """
        try:
            logger.info("Listing RDS database instances")
            response = self.client.describe_db_instances()

            instances = []
            for db_instance in response["DBInstances"]:
                instance_info = {
                    "db_instance_identifier": db_instance["DBInstanceIdentifier"],
                    "db_instance_class": db_instance["DBInstanceClass"],
                    "engine": db_instance["Engine"],
                    "engine_version": db_instance["EngineVersion"],
                    "db_instance_status": db_instance["DBInstanceStatus"],
                    "endpoint": db_instance.get("Endpoint", {}).get("Address"),
                    "port": db_instance.get("Endpoint", {}).get("Port"),
                    "availability_zone": db_instance.get("AvailabilityZone"),
                    "multi_az": db_instance.get("MultiAZ", False),
                    "read_replica_source": db_instance.get("ReadReplicaSourceDBInstanceIdentifier"),
                    "read_replicas": db_instance.get("ReadReplicaDBInstanceIdentifiers", []),
                    "backup_retention_period": db_instance.get("BackupRetentionPeriod"),
                    "allocated_storage": db_instance.get("AllocatedStorage"),
                    "storage_type": db_instance.get("StorageType"),
                    "storage_encrypted": db_instance.get("StorageEncrypted", False),
                    "instance_create_time": db_instance.get("InstanceCreateTime"),
                }
                instances.append(instance_info)

            logger.info(f"Found {len(instances)} RDS instances")
            return instances

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"AWS error listing RDS instances: {error_code}")
            raise RDSError(f"AWS error listing instances: {error_code}") from e
        except Exception as e:
            logger.error(f"Unexpected error listing RDS instances: {e}")
            raise RDSError(f"Unexpected error listing instances: {e}") from e

    async def list_db_clusters(self) -> list[dict[str, Any]]:
        """
        List all RDS database clusters in the region.

        Returns:
            List of database cluster metadata dictionaries

        Raises:
            RDSError: If listing clusters fails
        """
        try:
            logger.info("Listing RDS database clusters")
            response = self.client.describe_db_clusters()

            clusters = []
            for db_cluster in response["DBClusters"]:
                cluster_info = {
                    "db_cluster_identifier": db_cluster["DBClusterIdentifier"],
                    "engine": db_cluster["Engine"],
                    "engine_version": db_cluster["EngineVersion"],
                    "status": db_cluster["Status"],
                    "endpoint": db_cluster.get("Endpoint"),
                    "reader_endpoint": db_cluster.get("ReaderEndpoint"),
                    "port": db_cluster.get("Port"),
                    "master_username": db_cluster.get("MasterUsername"),
                    "database_name": db_cluster.get("DatabaseName"),
                    "cluster_members": [
                        {
                            "db_instance_identifier": member["DBInstanceIdentifier"],
                            "is_cluster_writer": member["IsClusterWriter"],
                            "promotion_tier": member.get("PromotionTier"),
                        }
                        for member in db_cluster.get("DBClusterMembers", [])
                    ],
                    "backup_retention_period": db_cluster.get("BackupRetentionPeriod"),
                    "storage_encrypted": db_cluster.get("StorageEncrypted", False),
                    "cluster_create_time": db_cluster.get("ClusterCreateTime"),
                    "availability_zones": db_cluster.get("AvailabilityZones", []),
                }
                clusters.append(cluster_info)

            logger.info(f"Found {len(clusters)} RDS clusters")
            return clusters

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"AWS error listing RDS clusters: {error_code}")
            raise RDSError(f"AWS error listing clusters: {error_code}") from e
        except Exception as e:
            logger.error(f"Unexpected error listing RDS clusters: {e}")
            raise RDSError(f"Unexpected error listing clusters: {e}") from e

    async def get_db_instance(self, instance_identifier: str) -> dict[str, Any]:
        """
        Get detailed information about a specific RDS instance.

        Args:
            instance_identifier: RDS instance identifier

        Returns:
            Dictionary with detailed instance information

        Raises:
            RDSError: If getting instance info fails
        """
        try:
            logger.info(f"Getting RDS instance details for {instance_identifier}")
            response = self.client.describe_db_instances(DBInstanceIdentifier=instance_identifier)

            if not response["DBInstances"]:
                raise RDSError(f"Instance {instance_identifier} not found")

            db_instance = response["DBInstances"][0]

            return {
                "db_instance_identifier": db_instance["DBInstanceIdentifier"],
                "db_instance_class": db_instance["DBInstanceClass"],
                "engine": db_instance["Engine"],
                "engine_version": db_instance["EngineVersion"],
                "db_instance_status": db_instance["DBInstanceStatus"],
                "endpoint": db_instance.get("Endpoint", {}).get("Address"),
                "port": db_instance.get("Endpoint", {}).get("Port"),
                "availability_zone": db_instance.get("AvailabilityZone"),
                "multi_az": db_instance.get("MultiAZ", False),
                "read_replica_source": db_instance.get("ReadReplicaSourceDBInstanceIdentifier"),
                "read_replicas": db_instance.get("ReadReplicaDBInstanceIdentifiers", []),
                "backup_retention_period": db_instance.get("BackupRetentionPeriod"),
                "allocated_storage": db_instance.get("AllocatedStorage"),
                "storage_type": db_instance.get("StorageType"),
                "storage_encrypted": db_instance.get("StorageEncrypted", False),
                "instance_create_time": db_instance.get("InstanceCreateTime"),
                "vpc_security_groups": [
                    {
                        "vpc_security_group_id": sg["VpcSecurityGroupId"],
                        "status": sg["Status"],
                    }
                    for sg in db_instance.get("VpcSecurityGroups", [])
                ],
                "db_parameter_groups": [
                    {
                        "db_parameter_group_name": pg["DBParameterGroupName"],
                        "parameter_apply_status": pg["ParameterApplyStatus"],
                    }
                    for pg in db_instance.get("DBParameterGroups", [])
                ],
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "DBInstanceNotFoundFault":
                raise RDSError(f"Instance {instance_identifier} not found") from e
            logger.error(f"AWS error getting RDS instance {instance_identifier}: {error_code}")
            raise RDSError(f"AWS error getting instance: {error_code}") from e
        except Exception as e:
            logger.error(f"Unexpected error getting RDS instance {instance_identifier}: {e}")
            raise RDSError(f"Unexpected error getting instance: {e}") from e

    async def discover_replication_topology(self) -> dict[str, Any]:
        """
        Discover physical replication topology across RDS instances and clusters.

        Returns:
            Dictionary containing replication topology information

        Raises:
            RDSError: If topology discovery fails
        """
        try:
            logger.info("Discovering RDS replication topology")

            # Get all instances and clusters
            instances = await self.list_db_instances()
            clusters = await self.list_db_clusters()

            # Build replication relationships
            replication_topology = {
                "discovery_time": datetime.now().isoformat(),
                "total_instances": len(instances),
                "total_clusters": len(clusters),
                "primary_instances": [],
                "read_replicas": [],
                "clusters": [],
                "replication_chains": [],
            }

            # Process instances
            primary_instances = []
            read_replicas = []

            for instance in instances:
                if instance["read_replica_source"]:
                    # This is a read replica
                    replica_info = {
                        "replica_identifier": instance["db_instance_identifier"],
                        "source_identifier": instance["read_replica_source"],
                        "engine": instance["engine"],
                        "status": instance["db_instance_status"],
                        "endpoint": instance["endpoint"],
                        "availability_zone": instance["availability_zone"],
                    }
                    read_replicas.append(replica_info)
                else:
                    # This is a primary instance
                    primary_info = {
                        "primary_identifier": instance["db_instance_identifier"],
                        "engine": instance["engine"],
                        "status": instance["db_instance_status"],
                        "endpoint": instance["endpoint"],
                        "read_replicas": instance["read_replicas"],
                        "availability_zone": instance["availability_zone"],
                        "multi_az": instance["multi_az"],
                    }
                    primary_instances.append(primary_info)

            # Process clusters
            cluster_info = []
            for cluster in clusters:
                cluster_data = {
                    "cluster_identifier": cluster["db_cluster_identifier"],
                    "engine": cluster["engine"],
                    "status": cluster["status"],
                    "writer_endpoint": cluster["endpoint"],
                    "reader_endpoint": cluster["reader_endpoint"],
                    "members": cluster["cluster_members"],
                    "availability_zones": cluster["availability_zones"],
                }
                cluster_info.append(cluster_data)

            # Build replication chains
            replication_chains = []
            for primary in primary_instances:
                if primary["read_replicas"]:
                    chain = {
                        "primary": primary["primary_identifier"],
                        "replicas": primary["read_replicas"],
                        "chain_length": len(primary["read_replicas"]),
                    }
                    replication_chains.append(chain)

            replication_topology.update(
                {
                    "primary_instances": primary_instances,
                    "read_replicas": read_replicas,
                    "clusters": cluster_info,
                    "replication_chains": replication_chains,
                }
            )

            logger.info(
                f"Discovered topology: {len(primary_instances)} primaries, "
                f"{len(read_replicas)} replicas, {len(clusters)} clusters"
            )

            return replication_topology

        except Exception as e:
            logger.error(f"Error discovering replication topology: {e}")
            raise RDSError(f"Error discovering topology: {e}") from e

    async def generate_auth_token(
        self, db_hostname: str, port: int, db_username: str, region: str | None = None
    ) -> str:
        """
        Generate IAM authentication token for RDS connection.

        Args:
            db_hostname: RDS instance hostname
            port: Database port
            db_username: Database username
            region: AWS region (uses client region if not specified)

        Returns:
            IAM authentication token

        Raises:
            RDSError: If token generation fails
        """
        try:
            region = region or self.region_name
            logger.info(f"Generating IAM auth token for {db_username}@{db_hostname}:{port}")

            token = self.client.generate_db_auth_token(
                DBHostname=db_hostname,
                Port=port,
                DBUsername=db_username,
                Region=region,
            )

            logger.info("Successfully generated IAM auth token")
            return token

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"AWS error generating auth token: {error_code}")
            raise RDSError(f"AWS error generating auth token: {error_code}") from e
        except Exception as e:
            logger.error(f"Unexpected error generating auth token: {e}")
            raise RDSError(f"Unexpected error generating auth token: {e}") from e
