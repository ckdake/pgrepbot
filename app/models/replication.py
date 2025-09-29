"""
Replication stream models
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from app.utils.redis_serializer import RedisModelMixin

# Custom datetime serializer
DatetimeSerializer = Annotated[datetime, PlainSerializer(lambda dt: dt.isoformat(), return_type=str)]

OptionalDatetimeSerializer = Annotated[
    datetime | None,
    PlainSerializer(lambda dt: dt.isoformat() if dt else None, return_type=str | None),
]


class ReplicationStream(BaseModel, RedisModelMixin):
    """Replication stream model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_db_id: str = Field(..., description="Source database ID")
    target_db_id: str = Field(..., description="Target database ID")
    type: Literal["logical", "physical"] = Field(..., description="Type of replication")

    # Logical replication specific fields
    publication_name: str | None = Field(None, description="PostgreSQL publication name")
    subscription_name: str | None = Field(None, description="PostgreSQL subscription name")

    # Physical replication specific fields
    replication_slot_name: str | None = Field(None, description="Replication slot name")
    wal_sender_pid: int | None = Field(None, description="WAL sender process ID")

    # Common fields
    status: Literal["active", "inactive", "error", "syncing"] = Field(..., description="Replication status")
    lag_bytes: int = Field(0, ge=0, description="Replication lag in bytes")
    lag_seconds: float = Field(0.0, ge=0.0, description="Replication lag in seconds")
    last_sync_time: OptionalDatetimeSerializer = Field(None, description="Last successful sync time")
    error_message: str | None = Field(None, description="Error message if status is error")
    is_managed: bool = Field(
        True,
        description=("Whether this stream can be modified (logical=true, physical=false)"),
    )
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    updated_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)

    @field_validator("source_db_id", "target_db_id")
    @classmethod
    def validate_db_ids(cls, v: str) -> str:
        """Validate database IDs are UUIDs"""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Database ID must be a valid UUID") from None
        return v

    @field_validator("publication_name", "subscription_name", "replication_slot_name")
    @classmethod
    def validate_postgres_names(cls, v: str | None) -> str | None:
        """Validate PostgreSQL object names"""
        if v is not None:
            if not v.replace("_", "").isalnum():
                raise ValueError("PostgreSQL names must contain only alphanumeric characters and underscores")
            if len(v) > 63:  # PostgreSQL identifier limit
                raise ValueError("PostgreSQL names must be 63 characters or less")
        return v


class ReplicationMetrics(BaseModel):
    """Replication metrics model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    stream_id: str
    timestamp: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    lag_bytes: int = Field(0, ge=0)
    lag_seconds: float = Field(0.0, ge=0.0)
    wal_position: str = Field(..., description="WAL LSN position")
    synced_tables: int = Field(0, ge=0)
    total_tables: int = Field(0, ge=0)
    backfill_progress: float | None = Field(None, ge=0.0, le=100.0, description="Backfill progress percentage")

    @field_validator("stream_id")
    @classmethod
    def validate_stream_id(cls, v: str) -> str:
        """Validate stream ID is UUID"""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Stream ID must be a valid UUID") from None
        return v

    @field_validator("wal_position")
    @classmethod
    def validate_wal_position(cls, v: str) -> str:
        """Validate WAL position format (LSN)"""
        if not v or "/" not in v:
            raise ValueError("WAL position must be in LSN format (e.g., 0/1234ABCD)")
        return v
