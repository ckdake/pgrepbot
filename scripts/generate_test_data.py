#!/usr/bin/env python3
"""
Simple test data generation script for PostgreSQL Replication Manager.
"""

import asyncio
import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta

import redis.asyncio as redis

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def generate_test_data():
    """Generate simple test data for testing"""
    try:
        # Connect to Redis
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True
        )
        
        await redis_client.ping()
        logger.info("✅ Connected to Redis")
        
        # Generate some test database configurations
        test_databases = []
        for i in range(5):
            db_config = {
                "id": f"test-db-{uuid.uuid4().hex[:8]}",
                "name": f"test-database-{i+1}",
                "host": f"db-{i+1}.example.com",
                "port": 5432 + i,
                "database": "testdb",
                "role": "primary" if i == 0 else "replica",
                "credentials_arn": f"arn:aws:secretsmanager:us-east-1:123456789012:secret:test-creds-{i+1}",
                "use_iam_auth": False,
                "cloud_provider": "aws",
                "region": "us-east-1",
                "description": f"Test database {i+1}",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            
            # Store in Redis
            key = f"database_config:{db_config['id']}"
            await redis_client.set(key, json.dumps(db_config))
            test_databases.append(db_config)
        
        logger.info(f"✅ Generated {len(test_databases)} test database configurations")
        
        # Generate some test alert thresholds
        test_thresholds = [
            {
                "id": f"test-threshold-{uuid.uuid4().hex[:8]}",
                "alert_type": "replication_lag",
                "severity": "warning",
                "metric_name": "replication_lag_seconds",
                "threshold_value": 300.0,
                "comparison_operator": "gt",
                "name": "Replication Lag Warning",
                "description": "Alert when replication lag exceeds 5 minutes",
                "enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
            {
                "id": f"test-threshold-{uuid.uuid4().hex[:8]}",
                "alert_type": "long_running_query",
                "severity": "warning",
                "metric_name": "long_running_query_count",
                "threshold_value": 1.0,
                "comparison_operator": "gte",
                "name": "Long Running Queries",
                "description": "Alert when queries run longer than 30 seconds",
                "enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        ]
        
        for threshold in test_thresholds:
            key = f"alert_threshold:{threshold['id']}"
            await redis_client.set(key, json.dumps(threshold))
        
        logger.info(f"✅ Generated {len(test_thresholds)} test alert thresholds")
        
        # Store summary
        summary = {
            "generated_at": datetime.utcnow().isoformat(),
            "databases": len(test_databases),
            "thresholds": len(test_thresholds),
        }
        
        await redis_client.set("test_data_summary", json.dumps(summary))
        
        logger.info("🎉 Test data generation completed successfully!")
        logger.info(f"📊 Generated: {summary['databases']} databases, {summary['thresholds']} thresholds")
        
        await redis_client.aclose()
        
    except Exception as e:
        logger.error(f"❌ Test data generation failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(generate_test_data())