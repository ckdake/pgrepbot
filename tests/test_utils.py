"""
Tests for utility functions.
"""

import json
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.utils.redis_serializer import RedisModelMixin, RedisSerializer


class SampleModel(BaseModel, RedisModelMixin):
    """Sample model for Redis serialization testing"""

    id: str
    name: str
    value: int


class TestRedisSerializer:
    """Test Redis serialization utilities"""

    def test_serialize_model(self):
        """Test serializing Pydantic model"""
        model = SampleModel(id="test-id", name="test", value=42)
        serialized = RedisSerializer.serialize(model)

        assert isinstance(serialized, str)
        data = json.loads(serialized)
        assert data["id"] == "test-id"
        assert data["name"] == "test"
        assert data["value"] == 42

    def test_deserialize_model(self):
        """Test deserializing to Pydantic model"""
        data = '{"id": "test-id", "name": "test", "value": 42}'

        model = RedisSerializer.deserialize(data, SampleModel)
        assert isinstance(model, SampleModel)
        assert model.id == "test-id"
        assert model.name == "test"
        assert model.value == 42

    def test_serialize_list(self):
        """Test serializing list of models"""
        models = [SampleModel(id="1", name="first", value=1), SampleModel(id="2", name="second", value=2)]

        serialized = RedisSerializer.serialize_list(models)
        assert isinstance(serialized, str)

        data = json.loads(serialized)
        assert len(data) == 2
        assert data[0]["id"] == "1"
        assert data[1]["id"] == "2"

    def test_deserialize_list(self):
        """Test deserializing list of models"""
        data = '[{"id": "1", "name": "first", "value": 1}, {"id": "2", "name": "second", "value": 2}]'

        models = RedisSerializer.deserialize_list(data, SampleModel)
        assert len(models) == 2
        assert all(isinstance(model, SampleModel) for model in models)
        assert models[0].id == "1"
        assert models[1].id == "2"

    def test_generate_key(self):
        """Test Redis key generation"""
        key = RedisSerializer.generate_key("test", "123")
        assert key == "pgrepman:test:123"

    def test_generate_list_key(self):
        """Test Redis list key generation"""
        key = RedisSerializer.generate_list_key("test")
        assert key == "pgrepman:test:all"

    def test_redis_model_mixin(self):
        """Test RedisModelMixin functionality"""
        model = SampleModel(id="test-id", name="test", value=42)

        # Test to_redis
        serialized = model.to_redis()
        assert isinstance(serialized, str)

        # Test from_redis
        deserialized = SampleModel.from_redis(serialized)
        assert deserialized.id == model.id
        assert deserialized.name == model.name
        assert deserialized.value == model.value

    def test_redis_key_generation(self):
        """Test Redis key generation for models"""
        model = SampleModel(id="test-id", name="test", value=42)
        key = model.redis_key("testmodel")
        assert key == "pgrepman:testmodel:test-id"

    @pytest.mark.asyncio
    async def test_save_and_load_from_redis(self):
        """Test saving and loading models from Redis"""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"id": "test-id", "name": "test", "value": 42}')

        model = SampleModel(id="test-id", name="test", value=42)

        # Test save
        await model.save_to_redis(mock_redis, "testmodel")
        mock_redis.set.assert_called_once()

        # Test load
        loaded_model = await SampleModel.load_from_redis(mock_redis, "test-id", "testmodel")
        assert loaded_model is not None
        assert loaded_model.id == "test-id"
