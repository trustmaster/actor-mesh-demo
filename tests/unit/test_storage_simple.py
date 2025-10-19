"""
Unit tests for simplified storage clients.

Tests the simplified Redis client for context caching functionality
used by the ContextRetriever actor.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from storage.redis_client_simple import SimplifiedRedisClient, get_simplified_redis_client, init_simplified_redis


class TestSimplifiedRedisClient:
    """Test cases for SimplifiedRedisClient."""

    def test_redis_client_initialization(self):
        """Test Redis client initialization."""
        client = SimplifiedRedisClient()
        assert client.redis_url == "redis://localhost:6379"
        assert client.db == 0
        assert client.CONTEXT_PREFIX == "context:"
        assert client.CONTEXT_TTL == 7200  # 2 hours
        assert client.redis is None

    def test_redis_client_custom_initialization(self):
        """Test Redis client with custom parameters."""
        client = SimplifiedRedisClient(redis_url="redis://custom:6380", db=1)
        assert client.redis_url == "redis://custom:6380"
        assert client.db == 1

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful Redis connection."""
        client = SimplifiedRedisClient()

        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis
            mock_redis.ping = AsyncMock()

            await client.connect()

            mock_from_url.assert_called_once_with(client.redis_url, db=0, decode_responses=True)
            mock_redis.ping.assert_called_once()
            assert client.redis == mock_redis

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test Redis connection failure."""
        client = SimplifiedRedisClient()

        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis
            mock_redis.ping = AsyncMock(side_effect=Exception("Connection failed"))

            with pytest.raises(Exception, match="Connection failed"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test Redis disconnection."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()

        await client.disconnect()

        client.redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connected(self):
        """Test ensuring connection is active."""
        client = SimplifiedRedisClient()

        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            await client._ensure_connected()
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_customer_context(self):
        """Test caching customer context."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()

        context_data = {"customer_id": "123", "tier": "gold"}
        email = "test@example.com"

        await client.cache_customer_context(email, context_data)

        expected_key = f"context:{email}"
        expected_value = json.dumps(context_data)
        client.redis.setex.assert_called_once_with(expected_key, 7200, expected_value)

    @pytest.mark.asyncio
    async def test_cache_customer_context_custom_ttl(self):
        """Test caching customer context with custom TTL."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()

        context_data = {"customer_id": "123"}
        email = "test@example.com"
        custom_ttl = 3600

        await client.cache_customer_context(email, context_data, ttl=custom_ttl)

        expected_key = f"context:{email}"
        expected_value = json.dumps(context_data)
        client.redis.setex.assert_called_once_with(expected_key, custom_ttl, expected_value)

    @pytest.mark.asyncio
    async def test_get_customer_context_exists(self):
        """Test getting existing customer context."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()

        context_data = {"customer_id": "123", "tier": "gold"}
        client.redis.get.return_value = json.dumps(context_data)

        email = "test@example.com"
        result = await client.get_customer_context(email)

        expected_key = f"context:{email}"
        client.redis.get.assert_called_once_with(expected_key)
        assert result == context_data

    @pytest.mark.asyncio
    async def test_get_customer_context_not_exists(self):
        """Test getting non-existent customer context."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()
        client.redis.get.return_value = None

        email = "test@example.com"
        result = await client.get_customer_context(email)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_customer_context_corrupted_data(self):
        """Test handling corrupted JSON data."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()
        client.redis.get.return_value = "invalid json"

        email = "test@example.com"
        result = await client.get_customer_context(email)

        # Should clean up corrupted data
        expected_key = f"context:{email}"
        client.redis.delete.assert_called_once_with(expected_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_customer_context_exists(self):
        """Test updating existing customer context."""
        client = SimplifiedRedisClient()

        original_data = {"customer_id": "123", "tier": "silver"}
        updates = {"tier": "gold", "last_purchase": "2024-01-01"}
        expected_result = {"customer_id": "123", "tier": "gold", "last_purchase": "2024-01-01"}

        with patch.object(client, "get_customer_context", return_value=original_data) as mock_get:
            with patch.object(client, "cache_customer_context") as mock_cache:
                result = await client.update_customer_context("test@example.com", updates)

                assert result is True
                mock_get.assert_called_once_with("test@example.com")
                mock_cache.assert_called_once_with("test@example.com", expected_result)

    @pytest.mark.asyncio
    async def test_update_customer_context_not_exists(self):
        """Test updating non-existent customer context."""
        client = SimplifiedRedisClient()

        with patch.object(client, "get_customer_context", return_value=None):
            result = await client.update_customer_context("test@example.com", {"tier": "gold"})
            assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_customer_context(self):
        """Test invalidating customer context."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()
        client.redis.delete.return_value = 1

        email = "test@example.com"
        result = await client.invalidate_customer_context(email)

        expected_key = f"context:{email}"
        client.redis.delete.assert_called_once_with(expected_key)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalidate_customer_context_not_found(self):
        """Test invalidating non-existent customer context."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()
        client.redis.delete.return_value = 0

        result = await client.invalidate_customer_context("test@example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check when Redis is healthy."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()
        client.redis.set = AsyncMock()
        client.redis.get.return_value = "ok"
        client.redis.delete = AsyncMock()
        client.redis.info.return_value = {
            "connected_clients": 5,
            "used_memory_human": "1.2M",
            "uptime_in_seconds": 3600
        }

        result = await client.health_check()

        assert result["status"] == "healthy"
        assert result["test_passed"] is True
        assert result["connected_clients"] == 5
        assert result["used_memory"] == "1.2M"
        assert result["uptime"] == 3600

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check when Redis is unhealthy."""
        client = SimplifiedRedisClient()

        with patch.object(client, "_ensure_connected", side_effect=Exception("Connection error")):
            result = await client.health_check()

            assert result["status"] == "unhealthy"
            assert result["test_passed"] is False
            assert "error" in result


class TestSimplifiedRedisClientUtilities:
    """Test utility functions for simplified Redis client."""

    @pytest.mark.asyncio
    async def test_get_simplified_redis_client_not_connected(self):
        """Test getting Redis client when not connected."""
        with patch("storage.redis_client_simple.simplified_redis_client") as mock_client:
            mock_client.redis = None
            mock_client.connect = AsyncMock()

            result = await get_simplified_redis_client()

            mock_client.connect.assert_called_once()
            assert result == mock_client

    @pytest.mark.asyncio
    async def test_get_simplified_redis_client_already_connected(self):
        """Test getting Redis client when already connected."""
        with patch("storage.redis_client_simple.simplified_redis_client") as mock_client:
            mock_client.redis = AsyncMock()  # Already connected

            result = await get_simplified_redis_client()

            assert result == mock_client

    @pytest.mark.asyncio
    async def test_init_simplified_redis(self):
        """Test initializing simplified Redis client."""
        custom_url = "redis://custom:6380"

        with patch("storage.redis_client_simple.SimplifiedRedisClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value = mock_instance

            result = await init_simplified_redis(custom_url)

            MockClient.assert_called_once_with(custom_url)
            mock_instance.connect.assert_called_once()
            assert result == mock_instance


class TestSimplifiedRedisClientIntegration:
    """Integration tests for simplified Redis client operations."""

    @pytest.mark.asyncio
    async def test_context_lifecycle(self):
        """Test complete context lifecycle operations."""
        client = SimplifiedRedisClient()
        email = "lifecycle@example.com"

        # Mock Redis operations
        with patch.object(client, "_ensure_connected"):
            client.redis = AsyncMock()

            # Initially no context
            client.redis.get.return_value = None
            assert await client.get_customer_context(email) is None

            # Cache context
            context = {"tier": "silver", "orders": 5}
            await client.cache_customer_context(email, context)

            # Retrieve cached context
            client.redis.get.return_value = json.dumps(context)
            result = await client.get_customer_context(email)
            assert result == context

            # Update context
            client.redis.get.return_value = json.dumps(context)
            updated = await client.update_customer_context(email, {"tier": "gold"})
            assert updated is True

            # Invalidate context
            client.redis.delete.return_value = 1
            deleted = await client.invalidate_customer_context(email)
            assert deleted is True

    @pytest.mark.asyncio
    async def test_error_handling_scenarios(self):
        """Test various error handling scenarios."""
        client = SimplifiedRedisClient()

        # Connection failure during operation
        with patch.object(client, "_ensure_connected", side_effect=Exception("Connection lost")):
            with pytest.raises(Exception, match="Connection lost"):
                await client.cache_customer_context("test@example.com", {})

    @pytest.mark.asyncio
    async def test_data_types_handling(self):
        """Test handling of different data types in context."""
        client = SimplifiedRedisClient()
        client.redis = AsyncMock()

        # Complex nested data
        complex_context = {
            "profile": {"name": "John", "age": 30},
            "orders": [{"id": 1, "total": 99.99}, {"id": 2, "total": 49.99}],
            "preferences": {"currency": "USD", "notifications": True}
        }

        email = "complex@example.com"

        await client.cache_customer_context(email, complex_context)

        expected_key = f"context:{email}"
        expected_value = json.dumps(complex_context)
        client.redis.setex.assert_called_once_with(expected_key, 7200, expected_value)
