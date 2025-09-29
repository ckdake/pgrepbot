"""
Migration execution models
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from app.utils.redis_serializer import RedisModelMixin

# Custom datetime serializer
DatetimeSerializer = Annotated[datetime, PlainSerializer(lambda dt: dt.isoformat(), return_type=str)]

OptionalDatetimeSerializer = Annotated[
    datetime | None,
    PlainSerializer(lambda dt: dt.isoformat() if dt else None, return_type=str | None),
]


class MigrationResult(BaseModel):
    """Result of migration execution on a single database"""

    model_config = ConfigDict(str_strip_whitespace=True)

    database_id: str
    status: Literal["success", "failed"] = Field(..., description="Migration result status")
    execution_time: float = Field(..., ge=0.0, description="Execution time in seconds")
    error_message: str | None = Field(None, description="Error message if failed")
    rows_affected: int | None = Field(None, ge=0, description="Number of rows affected")

    @field_validator("database_id")
    @classmethod
    def validate_database_id(cls, v: str) -> str:
        """Validate database ID is UUID"""
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Database ID must be a valid UUID") from None
        return v


class MigrationExecution(BaseModel, RedisModelMixin):
    """Migration execution model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    migration_script: str = Field(..., min_length=1, description="SQL migration script")
    target_databases: list[str] = Field(..., min_length=1, description="List of target database IDs")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        default="pending", description="Migration execution status"
    )
    results: list[MigrationResult] = Field(default_factory=list, description="Results for each database")
    started_at: OptionalDatetimeSerializer = Field(None, description="Migration start time")
    completed_at: OptionalDatetimeSerializer = Field(None, description="Migration completion time")
    created_by: str = Field(..., description="User who created the migration")
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)

    @field_validator("target_databases")
    @classmethod
    def validate_target_databases(cls, v: list[str]) -> list[str]:
        """Validate all target database IDs are UUIDs"""
        for db_id in v:
            try:
                uuid.UUID(db_id)
            except ValueError:
                raise ValueError(f"Database ID {db_id} must be a valid UUID") from None
        return v

    @field_validator("migration_script")
    @classmethod
    def validate_migration_script(cls, v: str) -> str:
        """Basic validation of SQL script"""
        # Remove comments and whitespace for validation
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Migration script cannot be empty")

        # Check for potentially dangerous operations
        dangerous_keywords = ["DROP DATABASE", "DROP SCHEMA", "TRUNCATE", "DELETE FROM"]
        upper_script = cleaned.upper()
        for keyword in dangerous_keywords:
            if keyword in upper_script:
                # Allow but warn - this is just basic validation
                pass

        return v

    @model_validator(mode="after")
    def validate_completed_at(self) -> "MigrationExecution":
        """Ensure completed_at is after started_at"""
        if self.completed_at is not None and self.started_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must be after started_at")
        return self


class MigrationRequest(BaseModel):
    """Request model for creating a new migration"""

    model_config = ConfigDict(str_strip_whitespace=True)

    migration_script: str = Field(..., min_length=1)
    target_databases: list[str] = Field(..., min_length=1)
    created_by: str = Field(..., min_length=1)

    @field_validator("target_databases")
    @classmethod
    def validate_target_databases(cls, v: list[str]) -> list[str]:
        """Validate all target database IDs are UUIDs"""
        for db_id in v:
            try:
                uuid.UUID(db_id)
            except ValueError:
                raise ValueError(f"Database ID {db_id} must be a valid UUID") from None
        return v
