"""
Database configuration models
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from app.utils.redis_serializer import RedisModelMixin

# Custom datetime serializer
DatetimeSerializer = Annotated[datetime, PlainSerializer(lambda dt: dt.isoformat(), return_type=str)]


class DatabaseConfig(BaseModel, RedisModelMixin):
    """Database configuration model"""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable database name")
    host: str = Field(..., min_length=1, description="Database host address")
    port: int = Field(..., ge=1, le=65535, description="Database port")
    database: str = Field(..., min_length=1, description="Database name")
    credentials_arn: str = Field(..., min_length=1, description="AWS Secrets Manager ARN for credentials")
    role: Literal["primary", "replica"] = Field(..., description="Database role in replication")
    environment: str = Field(..., min_length=1, description="Environment (dev, staging, prod)")
    cloud_provider: Literal["aws", "gcp"] = Field(..., description="Cloud provider")
    vpc_id: str | None = Field(None, description="VPC ID where database is located")
    subnet_ids: list[str] | None = Field(None, description="Subnet IDs for database")
    security_group_ids: list[str] | None = Field(None, description="Security group IDs")
    use_iam_auth: bool = Field(False, description="Whether to use IAM authentication")
    created_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
    updated_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)

    @field_validator("credentials_arn")
    @classmethod
    def validate_credentials_arn(cls, v: str) -> str:
        """Validate AWS Secrets Manager ARN format"""
        if not v.startswith("arn:aws:secretsmanager:"):
            raise ValueError("credentials_arn must be a valid AWS Secrets Manager ARN")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate database name contains only allowed characters"""
        if not v.replace("-", "").replace("_", "").replace(" ", "").isalnum():
            raise ValueError("name must contain only alphanumeric characters, hyphens, underscores, and spaces")
        return v


class DatabaseConnectionTest(BaseModel):
    """Model for testing database connections"""

    model_config = ConfigDict()

    database_id: str
    success: bool
    message: str
    latency_ms: float | None = None
    tested_at: DatetimeSerializer = Field(default_factory=datetime.utcnow)
