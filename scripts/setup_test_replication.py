#!/usr/bin/env python3
"""
Script to set up test replication configuration for development.

This script populates Redis with test database configurations and
demonstrates the replication discovery functionality.
"""

import asyncio
import json
import logging
from datetime import datetime

import redis.asyncio as redis

from app.models.database import DatabaseConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def setup_test_databases():
    """Set up test database configurations in Redis."""
    try:
        # Connect to Redis
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        
        # Test Redis connection
        await redis_client.ping()
        logger.info("Connected to Redis successfully")

        # Create test database configurations
        primary_db = DatabaseConfig(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="Test Primary Database",
            host="localhost",
            port=5432,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:000000000000:secret:primary-db-creds",
            role="primary",
            environment="development",
            cloud_provider="aws",
            vpc_id="vpc-12345678",
            use_iam_auth=False,
        )

        replica_db = DatabaseConfig(
            id="550e8400-e29b-41d4-a716-446655440001",
            name="Test Replica Database",
            host="localhost",
            port=5433,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:000000000000:secret:replica-db-creds",
            role="replica",
            environment="development",
            cloud_provider="aws",
            vpc_id="vpc-12345678",
            use_iam_auth=False,
        )

        physical_replica_db = DatabaseConfig(
            id="550e8400-e29b-41d4-a716-446655440002",
            name="Test Physical Replica Database",
            host="localhost",
            port=5434,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:000000000000:secret:physical-replica-db-creds",
            role="replica",
            environment="development",
            cloud_provider="aws",
            vpc_id="vpc-12345678",
            use_iam_auth=False,
        )

        # Store in Redis
        await redis_client.set(
            f"database:{primary_db.id}",
            primary_db.model_dump_json(),
            ex=3600  # 1 hour TTL
        )
        
        await redis_client.set(
            f"database:{replica_db.id}",
            replica_db.model_dump_json(),
            ex=3600  # 1 hour TTL
        )
        
        await redis_client.set(
            f"database:{physical_replica_db.id}",
            physical_replica_db.model_dump_json(),
            ex=3600  # 1 hour TTL
        )

        logger.info("✅ Test database configurations stored in Redis")
        logger.info(f"   Primary DB: {primary_db.name} ({primary_db.id})")
        logger.info(f"   Replica DB: {replica_db.name} ({replica_db.id})")
        logger.info(f"   Physical Replica DB: {physical_replica_db.name} ({physical_replica_db.id})")

        logger.info("✅ Test database configurations stored (credentials will be in LocalStack Secrets Manager)")

        # Close Redis connection
        await redis_client.aclose()

        print("\n" + "="*60)
        print("🎉 Test replication setup complete!")
        print("="*60)
        print("\nYou can now test replication discovery:")
        print("1. Start the application: make run")
        print("2. Visit: http://localhost:8000/api/replication/discover")
        print("3. Check topology: http://localhost:8000/api/replication/topology")
        print("\nThe discovery should find:")
        print("- 1 logical replication stream (test_publication -> test_subscription)")
        print("- Database configurations for primary and replica")
        print("- Current replication metrics and lag information")

    except Exception as e:
        logger.error(f"Failed to set up test databases: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(setup_test_databases())