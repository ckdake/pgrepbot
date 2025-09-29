"""
API endpoints for testing data models and Redis operations
"""

import os
import uuid
from datetime import datetime
from typing import Any

import redis
from fastapi import APIRouter, HTTPException

from app.models.database import DatabaseConfig
from app.models.migration import MigrationExecution
from app.models.replication import ReplicationStream
from app.utils.redis_serializer import RedisSerializer

router = APIRouter(prefix="/api/models", tags=["Models Testing"])


# Redis connection
def get_redis_client():
    """Get Redis client connection"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(redis_url, decode_responses=True)


@router.get("/test", response_model=dict[str, Any])
async def test_models_and_redis():
    """Test data model validation and Redis storage/retrieval"""
    try:
        redis_client = get_redis_client()

        # Test Redis connection
        redis_client.ping()

        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "redis_connection": "success",
            "tests": {},
        }

        # Test 1: DatabaseConfig model
        try:
            db_config = DatabaseConfig(
                name="test-database",
                host="localhost",
                port=5432,
                database="testdb",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
                role="primary",
                environment="dev",
                cloud_provider="aws",
                use_iam_auth=True,
            )

            # Test Redis serialization
            redis_key = db_config.redis_key("database")
            redis_client.set(redis_key, db_config.to_redis())

            # Test Redis deserialization
            stored_data = redis_client.get(redis_key)
            retrieved_config = DatabaseConfig.from_redis(stored_data)

            results["tests"]["database_config"] = {
                "status": "success",
                "original_id": db_config.id,
                "retrieved_id": retrieved_config.id,
                "redis_key": redis_key,
                "validation": "passed",
            }

        except Exception as e:
            results["tests"]["database_config"] = {"status": "failed", "error": str(e)}

        # Test 2: ReplicationStream model
        try:
            source_id = str(uuid.uuid4())
            target_id = str(uuid.uuid4())

            repl_stream = ReplicationStream(
                source_db_id=source_id,
                target_db_id=target_id,
                type="logical",
                publication_name="test_publication",
                subscription_name="test_subscription",
                status="active",
                lag_bytes=1024,
                lag_seconds=0.5,
            )

            # Test Redis operations
            redis_key = repl_stream.redis_key("replication")
            redis_client.set(redis_key, repl_stream.to_redis())

            stored_data = redis_client.get(redis_key)
            retrieved_stream = ReplicationStream.from_redis(stored_data)

            results["tests"]["replication_stream"] = {
                "status": "success",
                "original_id": repl_stream.id,
                "retrieved_id": retrieved_stream.id,
                "type": retrieved_stream.type,
                "validation": "passed",
            }

        except Exception as e:
            results["tests"]["replication_stream"] = {
                "status": "failed",
                "error": str(e),
            }

        # Test 3: MigrationExecution model
        try:
            migration = MigrationExecution(
                migration_script=("CREATE TABLE test_table (id SERIAL PRIMARY KEY, name VARCHAR(100));"),
                target_databases=[str(uuid.uuid4()), str(uuid.uuid4())],
                created_by="test_user",
            )

            # Test Redis operations
            redis_key = migration.redis_key("migration")
            redis_client.set(redis_key, migration.to_redis())

            stored_data = redis_client.get(redis_key)
            retrieved_migration = MigrationExecution.from_redis(stored_data)

            results["tests"]["migration_execution"] = {
                "status": "success",
                "original_id": migration.id,
                "retrieved_id": retrieved_migration.id,
                "target_count": len(retrieved_migration.target_databases),
                "validation": "passed",
            }

        except Exception as e:
            results["tests"]["migration_execution"] = {
                "status": "failed",
                "error": str(e),
            }

        # Test 4: List serialization
        try:
            configs = []
            for i in range(3):
                config = DatabaseConfig(
                    name=f"test-db-{i}",
                    host=f"host{i}.example.com",
                    port=5432 + i,
                    database=f"testdb{i}",
                    credentials_arn=f"arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret-{i}",
                    role="replica" if i > 0 else "primary",
                    environment="dev",
                    cloud_provider="aws",
                )
                configs.append(config)

            # Test list serialization
            list_key = RedisSerializer.generate_list_key("databases")
            serialized_list = RedisSerializer.serialize_list(configs)
            redis_client.set(list_key, serialized_list)

            # Test list deserialization
            stored_list = redis_client.get(list_key)
            retrieved_configs = RedisSerializer.deserialize_list(stored_list, DatabaseConfig)

            results["tests"]["list_serialization"] = {
                "status": "success",
                "original_count": len(configs),
                "retrieved_count": len(retrieved_configs),
                "validation": "passed",
            }

        except Exception as e:
            results["tests"]["list_serialization"] = {
                "status": "failed",
                "error": str(e),
            }

        # Test 5: Model validation errors
        try:
            # This should fail validation
            try:
                DatabaseConfig(
                    name="test-db",
                    host="localhost",
                    port=70000,  # Invalid port
                    database="testdb",
                    credentials_arn="invalid-arn",  # Invalid ARN
                    role="primary",
                    environment="dev",
                    cloud_provider="aws",
                )
                results["tests"]["validation_errors"] = {
                    "status": "failed",
                    "error": "Validation should have failed but didn't",
                }
            except Exception as validation_error:
                results["tests"]["validation_errors"] = {
                    "status": "success",
                    "validation_error_caught": str(validation_error),
                    "validation": "passed",
                }

        except Exception as e:
            results["tests"]["validation_errors"] = {
                "status": "failed",
                "error": str(e),
            }

        # Summary
        successful_tests = sum(1 for test in results["tests"].values() if test["status"] == "success")
        total_tests = len(results["tests"])

        results["summary"] = {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": total_tests - successful_tests,
            "success_rate": f"{(successful_tests / total_tests * 100):.1f}%",
        }

        return results

    except redis.ConnectionError:
        raise HTTPException(status_code=503, detail="Redis connection failed") from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test execution failed: {str(e)}") from e


@router.post("/database", response_model=DatabaseConfig)
async def create_test_database(config: DatabaseConfig):
    """Create a test database configuration"""
    try:
        redis_client = get_redis_client()
        redis_key = config.redis_key("database")
        redis_client.set(redis_key, config.to_redis())
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create database config: {str(e)}") from e


@router.get("/database/{db_id}", response_model=DatabaseConfig)
async def get_test_database(db_id: str):
    """Retrieve a test database configuration"""
    try:
        redis_client = get_redis_client()
        redis_key = RedisSerializer.generate_key("database", db_id)
        stored_data = redis_client.get(redis_key)

        if not stored_data:
            raise HTTPException(status_code=404, detail="Database configuration not found")

        return DatabaseConfig.from_redis(stored_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve database config: {str(e)}") from e


@router.get("/redis/keys")
async def list_redis_keys():
    """List all Redis keys for debugging"""
    try:
        redis_client = get_redis_client()
        keys = redis_client.keys("pgrepman:*")
        return {"keys": keys, "count": len(keys)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list Redis keys: {str(e)}") from e


@router.delete("/redis/clear")
async def clear_test_data():
    """Clear all test data from Redis"""
    try:
        redis_client = get_redis_client()
        keys = redis_client.keys("pgrepman:*")
        if keys:
            redis_client.delete(*keys)
        return {"message": f"Cleared {len(keys)} keys from Redis"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear Redis data: {str(e)}") from e
