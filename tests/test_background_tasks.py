"""
Tests for background tasks service.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.background_tasks import BackgroundTaskManager


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    return mock_client


@pytest.fixture
def task_manager(mock_redis):
    """Background task manager with mocked dependencies"""
    return BackgroundTaskManager(redis_client=mock_redis)


class TestBackgroundTaskManager:
    """Test background task manager functionality"""

    @pytest.mark.asyncio
    async def test_init(self, mock_redis):
        """Test background task manager initialization"""
        manager = BackgroundTaskManager(redis_client=mock_redis)
        assert manager.redis_client == mock_redis
        assert manager.running is False

    @pytest.mark.asyncio
    async def test_start_stop_tasks(self, task_manager):
        """Test starting and stopping background tasks"""
        # Mock the actual task methods that exist
        with patch.object(task_manager, "_run_monitoring_task") as mock_monitor:
            mock_monitor.return_value = asyncio.create_task(asyncio.sleep(0.1))

            # Start tasks
            await task_manager.start_all_tasks()
            assert task_manager.running is True

            # Stop tasks
            await task_manager.stop_all_tasks()
            assert task_manager.running is False

    @pytest.mark.asyncio
    async def test_get_task_status(self, task_manager):
        """Test getting task status"""
        status = task_manager.get_task_status()

        assert isinstance(status, dict)
        assert "running" in status
        assert "tasks" in status
        assert status["running"] is False
