#!/usr/bin/env python3
"""
Validation script for PostgreSQL Replication Manager.

Checks that all services are running and configured correctly.
"""

import asyncio
import asyncpg
import boto3
import json
import logging
import redis.asyncio as redis
import sys
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


async def validate_redis():
    """Validate Redis connection."""
    try:
        client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        await client.ping()
        await client.aclose()
        logger.info("✅ Redis: Connected")
        return True
    except Exception as e:
        logger.error(f"❌ Redis: {e}")
        return False


def validate_localstack():
    """Validate LocalStack connection and secrets."""
    try:
        client = boto3.client(
            'secretsmanager',
            endpoint_url='http://localhost:4566',
            aws_access_key_id='test',
            aws_secret_access_key='test',
            region_name='us-east-1'
        )
        
        required_secrets = [
            "primary-db-creds",
            "replica-db-creds",
            "physical-replica-db-creds"
        ]
        
        for secret in required_secrets:
            try:
                response = client.get_secret_value(SecretId=secret)
                data = json.loads(response['SecretString'])
                host = data.get('host', 'unknown')
                logger.info(f"✅ LocalStack: {secret} (host: {host})")
            except ClientError:
                logger.error(f"❌ LocalStack: {secret} not found")
                return False
                
        return True
    except Exception as e:
        logger.error(f"❌ LocalStack: {e}")
        return False


async def validate_postgres():
    """Validate PostgreSQL connections."""
    databases = [
        {"name": "Primary", "port": 5432},
        {"name": "Replica", "port": 5433},
        {"name": "Physical Replica", "port": 5434}
    ]
    
    all_good = True
    for db in databases:
        try:
            conn = await asyncpg.connect(
                host="localhost",
                port=db["port"],
                database="testdb",
                user="testuser",
                password="testpass",
                timeout=5.0
            )
            await conn.close()
            logger.info(f"✅ PostgreSQL: {db['name']} ({db['port']})")
        except Exception as e:
            logger.error(f"❌ PostgreSQL: {db['name']} ({db['port']}) - {e}")
            all_good = False
            
    return all_good


async def validate_replication():
    """Validate replication streams are working."""
    try:
        # Check logical replication
        primary_conn = await asyncpg.connect(
            host="localhost", port=5432, database="testdb", 
            user="testuser", password="testpass", timeout=5.0
        )
        
        replica_conn = await asyncpg.connect(
            host="localhost", port=5433, database="testdb",
            user="testuser", password="testpass", timeout=5.0
        )
        
        # Check if publication exists
        pub_result = await primary_conn.fetchval(
            "SELECT COUNT(*) FROM pg_publication WHERE pubname = 'test_publication'"
        )
        
        # Check if subscription exists  
        sub_result = await replica_conn.fetchval(
            "SELECT COUNT(*) FROM pg_subscription WHERE subname = 'test_subscription'"
        )
        
        await primary_conn.close()
        await replica_conn.close()
        
        if pub_result > 0 and sub_result > 0:
            logger.info("✅ Replication: Logical replication configured")
            return True
        else:
            logger.error(f"❌ Replication: Publication={pub_result}, Subscription={sub_result}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Replication: {e}")
        return False


async def validate_application():
    """Validate application endpoints and functionality."""
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test root endpoint
            response = await client.get("http://localhost:8000/")
            if response.status_code == 200:
                logger.info("✅ Application: Root endpoint")
            else:
                logger.error(f"❌ Application: Root endpoint ({response.status_code})")
                return False
                
            # Test database connections - should see all 3 databases
            response = await client.get("http://localhost:8000/api/databases/test")
            if response.status_code == 200:
                data = response.json()
                db_count = len(data.get("databases", []))
                total_count = data.get("total_databases", 0)
                healthy_count = data.get("healthy_databases", 0)
                logger.info(f"✅ Application: Database connections ({db_count} databases, {healthy_count} healthy)")
                if db_count != 3:
                    logger.error(f"❌ Application: Expected 3 databases, found {db_count}")
                    return False
                if healthy_count != 3:
                    logger.error(f"❌ Application: Expected 3 healthy databases, found {healthy_count}")
                    return False
            else:
                logger.error(f"❌ Application: Database test endpoint ({response.status_code})")
                return False
                
            # Test replication discovery - should find replication streams
            response = await client.get("http://localhost:8000/api/replication/discover")
            if response.status_code == 200:
                data = response.json()
                logical_streams = len(data.get("logical_streams", []))
                physical_streams = len(data.get("physical_streams", []))
                total_streams = data.get("total_streams", 0)
                logger.info(f"✅ Application: Replication discovery ({total_streams} streams: {logical_streams} logical, {physical_streams} physical)")
                if total_streams != 2:
                    logger.error(f"❌ Application: Expected 2 replication streams, found {total_streams}")
                    return False
                if logical_streams != 1:
                    logger.error(f"❌ Application: Expected 1 logical stream, found {logical_streams}")
                    return False
                if physical_streams != 1:
                    logger.error(f"❌ Application: Expected 1 physical stream, found {physical_streams}")
                    return False
            else:
                logger.error(f"❌ Application: Replication discovery ({response.status_code})")
                return False
                
            # Test replication topology - should show complete topology
            response = await client.get("http://localhost:8000/api/replication/topology")
            if response.status_code == 200:
                data = response.json()
                databases = len(data.get("databases", []))
                streams = len(data.get("streams", []))
                topology_summary = data.get("topology_map", {}).get("summary", {})
                total_dbs = topology_summary.get("total_databases", 0)
                total_streams = topology_summary.get("total_streams", 0)
                logger.info(f"✅ Application: Replication topology ({total_dbs} databases, {total_streams} streams)")
                if total_dbs != 3:
                    logger.error(f"❌ Application: Expected 3 databases in topology, found {total_dbs}")
                    return False
                if total_streams != 2:
                    logger.error(f"❌ Application: Expected 2 streams in topology, found {total_streams}")
                    return False
            else:
                logger.error(f"❌ Application: Replication topology ({response.status_code})")
                return False
                
        return True
    except Exception as e:
        logger.error(f"❌ Application: {e}")
        return False


async def main():
    """Run all validations."""
    print("🔍 Validating PostgreSQL Replication Manager")
    print("=" * 50)
    
    results = []
    
    # Validate services
    results.append(await validate_redis())
    results.append(validate_localstack())
    results.append(await validate_postgres())
    results.append(await validate_replication())
    results.append(await validate_application())
    
    print("=" * 50)
    
    if all(results):
        print("🎉 All validations passed!")
        return 0
    else:
        print("❌ Some validations failed!")
        print("💡 Try: make clean && make dev-services && make run")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))