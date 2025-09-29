"""
Redis serialization utilities for Pydantic models
"""

import json
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class RedisSerializer:
    """Utility class for serializing/deserializing Pydantic models to/from Redis"""

    @staticmethod
    def serialize(model: BaseModel) -> str:
        """Serialize a Pydantic model to JSON string for Redis storage"""
        return model.model_dump_json()

    @staticmethod
    def deserialize(data: str, model_class: type[T]) -> T:
        """Deserialize JSON string from Redis to Pydantic model"""
        return model_class.model_validate_json(data)

    @staticmethod
    def serialize_list(models: list[BaseModel]) -> str:
        """Serialize a list of Pydantic models to JSON string"""
        return json.dumps([model.model_dump() for model in models], cls=DateTimeEncoder)

    @staticmethod
    def deserialize_list(data: str, model_class: type[T]) -> list[T]:
        """Deserialize JSON string to list of Pydantic models"""
        json_list = json.loads(data)
        return [model_class.model_validate(item) for item in json_list]

    @staticmethod
    def generate_key(prefix: str, identifier: str) -> str:
        """Generate a Redis key with consistent format"""
        return f"pgrepman:{prefix}:{identifier}"

    @staticmethod
    def generate_list_key(prefix: str) -> str:
        """Generate a Redis key for lists"""
        return f"pgrepman:{prefix}:all"

    @staticmethod
    def generate_index_key(prefix: str, field: str, value: str) -> str:
        """Generate a Redis key for indexing"""
        return f"pgrepman:{prefix}:index:{field}:{value}"


class RedisModelMixin:
    """Mixin class to add Redis serialization methods to Pydantic models"""

    def to_redis(self) -> str:
        """Serialize this model to Redis format"""
        return RedisSerializer.serialize(self)

    @classmethod
    def from_redis(cls: type[T], data: str) -> T:
        """Deserialize from Redis format to model instance"""
        return RedisSerializer.deserialize(data, cls)

    def redis_key(self, prefix: str) -> str:
        """Generate Redis key for this model instance"""
        # Try different ID field names
        for id_field in ["id", "session_id"]:
            if hasattr(self, id_field):
                return RedisSerializer.generate_key(prefix, getattr(self, id_field))
        raise AttributeError("Model must have 'id' or 'session_id' attribute to generate Redis key")

    async def save_to_redis(self, redis_client, prefix: str | None = None) -> None:
        """Save this model to Redis"""
        if prefix is None:
            # Use class name as default prefix
            prefix = self.__class__.__name__.lower()

        key = self.redis_key(prefix)
        await redis_client.set(key, self.to_redis())

    @classmethod
    async def load_from_redis(cls: type[T], redis_client, model_id: str, prefix: str | None = None) -> T | None:
        """Load model from Redis by ID"""
        if prefix is None:
            prefix = cls.__name__.lower()

        key = RedisSerializer.generate_key(prefix, model_id)
        data = await redis_client.get(key)

        if data:
            return cls.from_redis(data)
        return None


# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
