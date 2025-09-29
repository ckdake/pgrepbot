"""
Tests for data models and Redis serialization
"""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models.database import DatabaseConfig
from app.models.migration import MigrationExecution, MigrationResult
from app.models.replication import ReplicationMetrics, ReplicationStream
from app.utils.redis_serializer import RedisSerializer


class TestDatabaseConfig:
    """Test DatabaseConfig model"""

    def test_valid_database_config(self):
        """Test creating a valid database configuration"""
        config = DatabaseConfig(
            name="test-db",
            host="localhost",
            port=5432,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
            role="primary",
            environment="dev",
            cloud_provider="aws",
        )

        assert config.name == "test-db"
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.role == "primary"
        assert config.cloud_provider == "aws"
        assert isinstance(config.id, str)
        assert isinstance(config.created_at, datetime)

    def test_invalid_credentials_arn(self):
        """Test validation of credentials ARN"""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                name="test-db",
                host="localhost",
                port=5432,
                database="testdb",
                credentials_arn="invalid-arn",
                role="primary",
                environment="dev",
                cloud_provider="aws",
            )

        assert "credentials_arn must be a valid AWS Secrets Manager ARN" in str(exc_info.value)

    def test_invalid_port(self):
        """Test port validation"""
        with pytest.raises(ValidationError):
            DatabaseConfig(
                name="test-db",
                host="localhost",
                port=70000,  # Invalid port
                database="testdb",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
                role="primary",
                environment="dev",
                cloud_provider="aws",
            )

    def test_invalid_name_characters(self):
        """Test name validation with invalid characters"""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                name="test@db!",  # Invalid characters
                host="localhost",
                port=5432,
                database="testdb",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
                role="primary",
                environment="dev",
                cloud_provider="aws",
            )

        assert "name must contain only alphanumeric characters" in str(exc_info.value)


class TestReplicationStream:
    """Test ReplicationStream model"""

    def test_valid_logical_replication_stream(self):
        """Test creating a valid logical replication stream"""
        source_id = str(uuid.uuid4())
        target_id = str(uuid.uuid4())

        stream = ReplicationStream(
            source_db_id=source_id,
            target_db_id=target_id,
            type="logical",
            publication_name="test_pub",
            subscription_name="test_sub",
            status="active",
            lag_bytes=1024,
            lag_seconds=0.5,
        )

        assert stream.source_db_id == source_id
        assert stream.target_db_id == target_id
        assert stream.type == "logical"
        assert stream.publication_name == "test_pub"
        assert stream.subscription_name == "test_sub"
        assert stream.is_managed is True

    def test_valid_physical_replication_stream(self):
        """Test creating a valid physical replication stream"""
        source_id = str(uuid.uuid4())
        target_id = str(uuid.uuid4())

        stream = ReplicationStream(
            source_db_id=source_id,
            target_db_id=target_id,
            type="physical",
            replication_slot_name="physical_slot",
            wal_sender_pid=12345,
            status="active",
            is_managed=False,
        )

        assert stream.type == "physical"
        assert stream.replication_slot_name == "physical_slot"
        assert stream.wal_sender_pid == 12345
        assert stream.is_managed is False

    def test_invalid_database_id(self):
        """Test validation of database IDs"""
        with pytest.raises(ValidationError) as exc_info:
            ReplicationStream(
                source_db_id="invalid-uuid",
                target_db_id=str(uuid.uuid4()),
                type="logical",
                status="active",
            )

        assert "Database ID must be a valid UUID" in str(exc_info.value)

    def test_invalid_postgres_name(self):
        """Test validation of PostgreSQL names"""
        source_id = str(uuid.uuid4())
        target_id = str(uuid.uuid4())

        with pytest.raises(ValidationError) as exc_info:
            ReplicationStream(
                source_db_id=source_id,
                target_db_id=target_id,
                type="logical",
                publication_name="test-pub!",  # Invalid character
                status="active",
            )

        assert "PostgreSQL names must contain only alphanumeric characters and underscores" in str(exc_info.value)


class TestMigrationExecution:
    """Test MigrationExecution model"""

    def test_valid_migration_execution(self):
        """Test creating a valid migration execution"""
        db_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        migration = MigrationExecution(
            migration_script="CREATE TABLE test (id SERIAL PRIMARY KEY);",
            target_databases=db_ids,
            created_by="test_user",
        )

        assert migration.migration_script == "CREATE TABLE test (id SERIAL PRIMARY KEY);"
        assert migration.target_databases == db_ids
        assert migration.created_by == "test_user"
        assert migration.status == "pending"
        assert isinstance(migration.id, str)

    def test_invalid_target_database_id(self):
        """Test validation of target database IDs"""
        with pytest.raises(ValidationError) as exc_info:
            MigrationExecution(
                migration_script="CREATE TABLE test (id SERIAL PRIMARY KEY);",
                target_databases=["invalid-uuid"],
                created_by="test_user",
            )

        assert "Database ID invalid-uuid must be a valid UUID" in str(exc_info.value)

    def test_empty_migration_script(self):
        """Test validation of empty migration script"""
        with pytest.raises(ValidationError) as exc_info:
            MigrationExecution(
                migration_script="   ",  # Empty after stripping
                target_databases=[str(uuid.uuid4())],
                created_by="test_user",
            )

        # In Pydantic v2, str_strip_whitespace=True causes this to fail
        # min_length validation
        assert "String should have at least 1 character" in str(exc_info.value)

    def test_migration_result(self):
        """Test MigrationResult model"""
        db_id = str(uuid.uuid4())

        result = MigrationResult(database_id=db_id, status="success", execution_time=1.5, rows_affected=10)

        assert result.database_id == db_id
        assert result.status == "success"
        assert result.execution_time == 1.5
        assert result.rows_affected == 10


class TestReplicationMetrics:
    """Test ReplicationMetrics model"""

    def test_valid_replication_metrics(self):
        """Test creating valid replication metrics"""
        stream_id = str(uuid.uuid4())

        metrics = ReplicationMetrics(
            stream_id=stream_id,
            lag_bytes=2048,
            lag_seconds=1.0,
            wal_position="0/1234ABCD",
            synced_tables=5,
            total_tables=10,
            backfill_progress=50.0,
        )

        assert metrics.stream_id == stream_id
        assert metrics.lag_bytes == 2048
        assert metrics.wal_position == "0/1234ABCD"
        assert metrics.backfill_progress == 50.0

    def test_invalid_wal_position(self):
        """Test validation of WAL position format"""
        stream_id = str(uuid.uuid4())

        with pytest.raises(ValidationError) as exc_info:
            ReplicationMetrics(
                stream_id=stream_id,
                wal_position="invalid-lsn",
                synced_tables=5,
                total_tables=10,
            )

        assert "WAL position must be in LSN format" in str(exc_info.value)


class TestRedisSerializer:
    """Test Redis serialization utilities"""

    def test_serialize_deserialize_database_config(self):
        """Test serializing and deserializing DatabaseConfig"""
        config = DatabaseConfig(
            name="test-db",
            host="localhost",
            port=5432,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
            role="primary",
            environment="dev",
            cloud_provider="aws",
        )

        # Serialize to Redis format
        serialized = RedisSerializer.serialize(config)
        assert isinstance(serialized, str)

        # Deserialize back to model
        deserialized = RedisSerializer.deserialize(serialized, DatabaseConfig)
        assert deserialized.name == config.name
        assert deserialized.host == config.host
        assert deserialized.port == config.port
        assert deserialized.id == config.id

    def test_serialize_deserialize_list(self):
        """Test serializing and deserializing list of models"""
        configs = [
            DatabaseConfig(
                name="db1",
                host="host1",
                port=5432,
                database="db1",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test1",
                role="primary",
                environment="dev",
                cloud_provider="aws",
            ),
            DatabaseConfig(
                name="db2",
                host="host2",
                port=5433,
                database="db2",
                credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test2",
                role="replica",
                environment="dev",
                cloud_provider="aws",
            ),
        ]

        # Serialize list
        serialized = RedisSerializer.serialize_list(configs)
        assert isinstance(serialized, str)

        # Deserialize back to list
        deserialized = RedisSerializer.deserialize_list(serialized, DatabaseConfig)
        assert len(deserialized) == 2
        assert deserialized[0].name == "db1"
        assert deserialized[1].name == "db2"

    def test_redis_key_generation(self):
        """Test Redis key generation"""
        key = RedisSerializer.generate_key("database", "test-id")
        assert key == "pgrepman:database:test-id"

        list_key = RedisSerializer.generate_list_key("databases")
        assert list_key == "pgrepman:databases:all"

        index_key = RedisSerializer.generate_index_key("database", "environment", "dev")
        assert index_key == "pgrepman:database:index:environment:dev"

    def test_model_redis_methods(self):
        """Test Redis mixin methods on models"""
        config = DatabaseConfig(
            name="test-db",
            host="localhost",
            port=5432,
            database="testdb",
            credentials_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret",
            role="primary",
            environment="dev",
            cloud_provider="aws",
        )

        # Test to_redis method
        serialized = config.to_redis()
        assert isinstance(serialized, str)

        # Test from_redis method
        deserialized = DatabaseConfig.from_redis(serialized)
        assert deserialized.name == config.name

        # Test redis_key method
        key = config.redis_key("database")
        assert key.startswith("pgrepman:database:")
        assert config.id in key
