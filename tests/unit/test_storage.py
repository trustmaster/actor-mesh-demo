"""
Unit tests for storage clients.

Tests the Redis and SQLite storage clients including session management,
context caching, database operations, and error handling scenarios.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from storage.redis_client import RedisClient, SessionState, get_redis_client, init_redis


class TestSessionState:
    """Test cases for SessionState model."""

    def test_session_state_creation(self):
        """Test creating a session state."""
        session = SessionState(
            session_id="test-session-123",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
        )

        assert session.session_id == "test-session-123"
        assert session.customer_email == "test@example.com"
        assert session.context == {}
        assert session.message_count == 0
        assert session.status == "active"

    def test_session_state_with_context(self):
        """Test session state with context data."""
        context = {
            "customer_tier": "premium",
            "last_order": "ORD-12345",
            "preferences": {"language": "en"},
        }

        session = SessionState(
            session_id="test-session-123",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
            context=context,
            message_count=5,
            status="escalated",
        )

        assert session.context == context
        assert session.message_count == 5
        assert session.status == "escalated"

    def test_session_state_serialization(self):
        """Test session state JSON serialization."""
        session = SessionState(
            session_id="test-session-123",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
            context={"test": "data"},
        )

        # Convert to JSON and back
        json_data = session.json()
        reconstructed = SessionState.parse_raw(json_data)

        assert reconstructed.session_id == session.session_id
        assert reconstructed.customer_email == session.customer_email
        assert reconstructed.context == session.context


class TestRedisClient:
    """Test cases for RedisClient class."""

    @pytest.fixture
    def redis_client(self):
        """Create a RedisClient instance for testing."""
        return RedisClient(redis_url="redis://localhost:6379", db=1)  # Use test DB

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis connection."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.incrby = AsyncMock(return_value=1)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.close = AsyncMock()
        mock_redis.info = AsyncMock(
            return_value={
                "connected_clients": 5,
                "used_memory_human": "1.5M",
                "uptime_in_seconds": 3600,
            }
        )
        mock_redis.scan_iter = AsyncMock(return_value=AsyncMock(__aiter__=lambda x: iter([])))
        return mock_redis

    def test_redis_client_initialization(self, redis_client):
        """Test Redis client initialization."""
        assert redis_client.redis_url == "redis://localhost:6379"
        assert redis_client.db == 1
        assert redis_client.redis is None

        # Check prefixes
        assert redis_client.SESSION_PREFIX == "session:"
        assert redis_client.CONTEXT_PREFIX == "context:"
        assert redis_client.TEMP_PREFIX == "temp:"
        assert redis_client.COUNTER_PREFIX == "counter:"

        # Check TTL values
        assert redis_client.SESSION_TTL == 3600 * 24
        assert redis_client.CONTEXT_TTL == 3600 * 2
        assert redis_client.TEMP_TTL == 300

    @pytest.mark.asyncio
    async def test_connect_success(self, redis_client, mock_redis):
        """Test successful Redis connection."""
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await redis_client.connect()

            assert redis_client.redis == mock_redis
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, redis_client):
        """Test Redis connection failure."""
        with patch("redis.asyncio.from_url", side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                await redis_client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, redis_client, mock_redis):
        """Test Redis disconnection."""
        redis_client.redis = mock_redis

        await redis_client.disconnect()

        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connected(self, redis_client, mock_redis):
        """Test automatic connection when needed."""
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await redis_client._ensure_connected()

            assert redis_client.redis == mock_redis

    @pytest.mark.asyncio
    async def test_create_session(self, redis_client, mock_redis):
        """Test session creation."""
        redis_client.redis = mock_redis

        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-15T10:30:00"

            session = await redis_client.create_session("test-session", "test@example.com")

            assert session.session_id == "test-session"
            assert session.customer_email == "test@example.com"
            assert session.created_at == "2024-01-15T10:30:00"
            assert session.last_activity == "2024-01-15T10:30:00"

            # Verify Redis call
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            assert call_args[0] == "session:test-session"
            assert call_args[1] == redis_client.SESSION_TTL

    @pytest.mark.asyncio
    async def test_get_session_exists(self, redis_client, mock_redis):
        """Test getting existing session."""
        redis_client.redis = mock_redis

        # Mock session data
        session_data = SessionState(
            session_id="test-session",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
        )
        mock_redis.get.return_value = session_data.json()

        session = await redis_client.get_session("test-session")

        assert session is not None
        assert session.session_id == "test-session"
        assert session.customer_email == "test@example.com"

        mock_redis.get.assert_called_once_with("session:test-session")

    @pytest.mark.asyncio
    async def test_get_session_not_exists(self, redis_client, mock_redis):
        """Test getting non-existent session."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None

        session = await redis_client.get_session("nonexistent")

        assert session is None
        mock_redis.get.assert_called_once_with("session:nonexistent")

    @pytest.mark.asyncio
    async def test_update_session_success(self, redis_client, mock_redis):
        """Test successful session update."""
        redis_client.redis = mock_redis

        # Mock existing session
        existing_session = SessionState(
            session_id="test-session",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
            message_count=5,
            status="active",
        )
        mock_redis.get.return_value = existing_session.json()

        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-15T11:00:00"

            result = await redis_client.update_session("test-session", status="escalated", message_count=10)

            assert result is True
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_session_not_found(self, redis_client, mock_redis):
        """Test updating non-existent session."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None

        result = await redis_client.update_session("nonexistent", status="escalated")

        assert result is False

    @pytest.mark.asyncio
    async def test_increment_message_count(self, redis_client, mock_redis):
        """Test incrementing message count."""
        redis_client.redis = mock_redis

        # Mock existing session
        existing_session = SessionState(
            session_id="test-session",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
            message_count=5,
        )
        mock_redis.get.return_value = existing_session.json()

        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-15T11:00:00"

            count = await redis_client.increment_message_count("test-session")

            assert count == 6
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_message_count_no_session(self, redis_client, mock_redis):
        """Test incrementing message count for non-existent session."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None

        count = await redis_client.increment_message_count("nonexistent")

        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_session(self, redis_client, mock_redis):
        """Test session deletion."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 1

        result = await redis_client.delete_session("test-session")

        assert result is True
        mock_redis.delete.assert_called_once_with("session:test-session")

    @pytest.mark.asyncio
    async def test_set_context(self, redis_client, mock_redis):
        """Test setting customer context."""
        redis_client.redis = mock_redis

        context_data = {
            "customer_tier": "premium",
            "last_order": "ORD-12345",
            "preferences": {"language": "en"},
        }

        await redis_client.set_context("test@example.com", context_data)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "context:test@example.com"
        assert call_args[1] == redis_client.CONTEXT_TTL
        assert json.loads(call_args[2]) == context_data

    @pytest.mark.asyncio
    async def test_get_context_exists(self, redis_client, mock_redis):
        """Test getting existing context."""
        redis_client.redis = mock_redis

        context_data = {"customer_tier": "premium"}
        mock_redis.get.return_value = json.dumps(context_data)

        result = await redis_client.get_context("test@example.com")

        assert result == context_data
        mock_redis.get.assert_called_once_with("context:test@example.com")

    @pytest.mark.asyncio
    async def test_get_context_not_exists(self, redis_client, mock_redis):
        """Test getting non-existent context."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None

        result = await redis_client.get_context("test@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_context(self, redis_client, mock_redis):
        """Test updating customer context."""
        redis_client.redis = mock_redis

        existing_context = {"customer_tier": "standard"}
        updates = {"last_order": "ORD-12345", "customer_tier": "premium"}
        expected_result = {"customer_tier": "premium", "last_order": "ORD-12345"}

        mock_redis.get.return_value = json.dumps(existing_context)

        await redis_client.update_context("test@example.com", updates)

        # Should have called setex with merged data
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert json.loads(call_args[2]) == expected_result

    @pytest.mark.asyncio
    async def test_update_context_no_existing(self, redis_client, mock_redis):
        """Test updating context when no existing context."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None

        updates = {"customer_tier": "premium"}

        await redis_client.update_context("test@example.com", updates)

        # Should create new context with updates
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert json.loads(call_args[2]) == updates

    @pytest.mark.asyncio
    async def test_delete_context(self, redis_client, mock_redis):
        """Test context deletion."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 1

        result = await redis_client.delete_context("test@example.com")

        assert result is True
        mock_redis.delete.assert_called_once_with("context:test@example.com")

    @pytest.mark.asyncio
    async def test_set_temp_data_dict(self, redis_client, mock_redis):
        """Test setting temporary data with dictionary."""
        redis_client.redis = mock_redis

        temp_data = {"key": "value", "number": 123}

        await redis_client.set_temp_data("test-key", temp_data, ttl=600)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "temp:test-key"
        assert call_args[1] == 600
        assert json.loads(call_args[2]) == temp_data

    @pytest.mark.asyncio
    async def test_set_temp_data_string(self, redis_client, mock_redis):
        """Test setting temporary data with string."""
        redis_client.redis = mock_redis

        await redis_client.set_temp_data("test-key", "test-value")

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == "temp:test-key"
        assert call_args[1] == redis_client.TEMP_TTL
        assert call_args[2] == "test-value"

    @pytest.mark.asyncio
    async def test_get_temp_data(self, redis_client, mock_redis):
        """Test getting temporary data."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = "test-value"

        result = await redis_client.get_temp_data("test-key")

        assert result == "test-value"
        mock_redis.get.assert_called_once_with("temp:test-key")

    @pytest.mark.asyncio
    async def test_delete_temp_data(self, redis_client, mock_redis):
        """Test deleting temporary data."""
        redis_client.redis = mock_redis
        mock_redis.delete.return_value = 1

        result = await redis_client.delete_temp_data("test-key")

        assert result is True
        mock_redis.delete.assert_called_once_with("temp:test-key")

    @pytest.mark.asyncio
    async def test_increment_counter(self, redis_client, mock_redis):
        """Test incrementing counter."""
        redis_client.redis = mock_redis
        mock_redis.incrby.return_value = 5

        result = await redis_client.increment_counter("test-counter", 3)

        assert result == 5
        mock_redis.incrby.assert_called_once_with("counter:test-counter", 3)

    @pytest.mark.asyncio
    async def test_increment_counter_default(self, redis_client, mock_redis):
        """Test incrementing counter with default amount."""
        redis_client.redis = mock_redis
        mock_redis.incrby.return_value = 1

        result = await redis_client.increment_counter("test-counter")

        assert result == 1
        mock_redis.incrby.assert_called_once_with("counter:test-counter", 1)

    @pytest.mark.asyncio
    async def test_get_counter_exists(self, redis_client, mock_redis):
        """Test getting existing counter."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = "42"

        result = await redis_client.get_counter("test-counter")

        assert result == 42
        mock_redis.get.assert_called_once_with("counter:test-counter")

    @pytest.mark.asyncio
    async def test_get_counter_not_exists(self, redis_client, mock_redis):
        """Test getting non-existent counter."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = None

        result = await redis_client.get_counter("test-counter")

        assert result == 0

    @pytest.mark.asyncio
    async def test_reset_counter(self, redis_client, mock_redis):
        """Test resetting counter."""
        redis_client.redis = mock_redis

        await redis_client.reset_counter("test-counter")

        mock_redis.set.assert_called_once_with("counter:test-counter", 0)

    @pytest.mark.asyncio
    async def test_get_sessions_by_customer(self, redis_client, mock_redis):
        """Test getting sessions by customer email."""
        redis_client.redis = mock_redis

        # Mock sessions
        session1 = SessionState(
            session_id="session-1",
            customer_email="test@example.com",
            created_at="2024-01-15T10:30:00",
            last_activity="2024-01-15T10:30:00",
        )
        session2 = SessionState(
            session_id="session-2",
            customer_email="other@example.com",
            created_at="2024-01-15T11:00:00",
            last_activity="2024-01-15T11:00:00",
        )
        session3 = SessionState(
            session_id="session-3",
            customer_email="test@example.com",
            created_at="2024-01-15T12:00:00",
            last_activity="2024-01-15T12:00:00",
        )

        # Mock scan_iter and get calls
        keys = ["session:session-1", "session:session-2", "session:session-3"]
        values = [session1.json(), session2.json(), session3.json()]

        async def mock_scan_iter(pattern):
            for key in keys:
                yield key

        async def mock_get(key):
            index = keys.index(key)
            return values[index]

        mock_redis.scan_iter.return_value = mock_scan_iter(None)
        mock_redis.get.side_effect = mock_get

        sessions = await redis_client.get_sessions_by_customer("test@example.com")

        assert len(sessions) == 2
        assert all(s.customer_email == "test@example.com" for s in sessions)
        assert {s.session_id for s in sessions} == {"session-1", "session-3"}

    @pytest.mark.asyncio
    async def test_cleanup_expired_data(self, redis_client, mock_redis):
        """Test cleanup expired data stats."""
        redis_client.redis = mock_redis

        # Mock different key counts
        async def mock_scan_iter(pattern):
            if "session:" in pattern:
                for i in range(3):
                    yield f"session:test-{i}"
            elif "context:" in pattern:
                for i in range(2):
                    yield f"context:test-{i}"
            elif "temp:" in pattern:
                for i in range(1):
                    yield f"temp:test-{i}"

        mock_redis.scan_iter.side_effect = mock_scan_iter

        stats = await redis_client.cleanup_expired_data()

        assert stats["sessions_active"] == 3
        assert stats["contexts_active"] == 2
        assert stats["temp_data_active"] == 1

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, redis_client, mock_redis):
        """Test health check when Redis is healthy."""
        redis_client.redis = mock_redis
        mock_redis.get.return_value = "ok"

        health = await redis_client.health_check()

        assert health["status"] == "healthy"
        assert health["test_passed"] is True
        assert health["connected_clients"] == 5
        assert health["used_memory"] == "1.5M"
        assert health["uptime"] == 3600

        # Verify test operations
        mock_redis.set.assert_called_once()
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, redis_client):
        """Test health check when Redis is unhealthy."""
        with patch("redis.asyncio.from_url", side_effect=Exception("Connection failed")):
            health = await redis_client.health_check()

            assert health["status"] == "unhealthy"
            assert health["test_passed"] is False
            assert "error" in health


class TestRedisClientUtilities:
    """Test cases for Redis client utility functions."""

    @pytest.mark.asyncio
    async def test_get_redis_client_not_connected(self):
        """Test get_redis_client when not connected."""
        with patch("storage.redis_client.redis_client") as mock_global_client:
            mock_global_client.redis = None
            mock_global_client.connect = AsyncMock()

            result = await get_redis_client()

            assert result == mock_global_client
            mock_global_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_redis_client_already_connected(self):
        """Test get_redis_client when already connected."""
        with patch("storage.redis_client.redis_client") as mock_global_client:
            mock_global_client.redis = MagicMock()

            result = await get_redis_client()

            assert result == mock_global_client
            # Should not call connect if already connected

    @pytest.mark.asyncio
    async def test_init_redis(self):
        """Test init_redis utility function."""
        with patch("storage.redis_client.RedisClient") as MockRedisClient:
            mock_instance = AsyncMock()
            MockRedisClient.return_value = mock_instance

            result = await init_redis("redis://test:6379")

            MockRedisClient.assert_called_once_with("redis://test:6379")
            mock_instance.connect.assert_called_once()
            assert result == mock_instance


class TestRedisClientIntegration:
    """Integration test cases for Redis client functionality."""

    @pytest.fixture
    def redis_client(self):
        """Create a RedisClient instance for integration testing."""
        return RedisClient(redis_url="redis://localhost:6379", db=15)  # Use test DB

    @pytest.mark.asyncio
    async def test_session_lifecycle(self, redis_client, mock_redis):
        """Test complete session lifecycle."""
        redis_client.redis = mock_redis

        # Mock different responses for different calls
        session_data = None

        async def mock_get(key):
            nonlocal session_data
            if session_data and key == "session:test-session":
                return session_data
            return None

        def mock_setex(key, ttl, data):
            nonlocal session_data
            if key == "session:test-session":
                session_data = data
            return True

        mock_redis.get.side_effect = mock_get
        mock_redis.setex.side_effect = mock_setex

        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-15T10:30:00"

            # Create session
            session = await redis_client.create_session("test-session", "test@example.com")
            assert session.session_id == "test-session"

            # Get session
            retrieved = await redis_client.get_session("test-session")
            assert retrieved is not None
            assert retrieved.session_id == "test-session"

            # Update session
            mock_datetime.utcnow.return_value.isoformat.return_value = "2024-01-15T11:00:00"
            result = await redis_client.update_session("test-session", status="escalated")
            assert result is True

            # Increment message count
            count = await redis_client.increment_message_count("test-session")
            assert count == 1

    @pytest.mark.asyncio
    async def test_context_operations(self, redis_client, mock_redis):
        """Test context operations workflow."""
        redis_client.redis = mock_redis

        context_data = None

        async def mock_get(key):
            nonlocal context_data
            if context_data and key == "context:test@example.com":
                return json.dumps(context_data)
            return None

        def mock_setex(key, ttl, data):
            nonlocal context_data
            if key == "context:test@example.com":
                context_data = json.loads(data)
            return True

        mock_redis.get.side_effect = mock_get
        mock_redis.setex.side_effect = mock_setex

        # Set initial context
        initial_context = {"customer_tier": "standard"}
        await redis_client.set_context("test@example.com", initial_context)

        # Get context
        retrieved = await redis_client.get_context("test@example.com")
        assert retrieved == initial_context

        # Update context
        updates = {"last_order": "ORD-12345", "customer_tier": "premium"}
        await redis_client.update_context("test@example.com", updates)

        # Verify updated context
        final_context = await redis_client.get_context("test@example.com")
        expected = {"customer_tier": "premium", "last_order": "ORD-12345"}
        assert final_context == expected

    @pytest.mark.asyncio
    async def test_error_handling_scenarios(self, redis_client):
        """Test various error handling scenarios."""
        # Test connection failure during operation
        redis_client.redis = None

        with patch("redis.asyncio.from_url", side_effect=Exception("Connection failed")):
            with pytest.raises(Exception):
                await redis_client.get_session("test")

        # Test Redis operation failure
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.get.side_effect = Exception("Redis operation failed")
        redis_client.redis = mock_redis

        with pytest.raises(Exception):
            await redis_client.get_session("test")

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, redis_client, mock_redis):
        """Test concurrent Redis operations."""
        import asyncio

        redis_client.redis = mock_redis
        mock_redis.get.return_value = None
        mock_redis.incrby.return_value = 1

        # Simulate concurrent counter increments
        tasks = [redis_client.increment_counter("concurrent_test") for _ in range(10)]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        assert all(result == 1 for result in results)  # Mock returns 1 each time

    @pytest.mark.asyncio
    async def test_data_types_handling(self, redis_client, mock_redis):
        """Test handling of different data types."""
        redis_client.redis = mock_redis

        test_cases = [
            ("string_data", "simple string"),
            ("dict_data", {"key": "value", "nested": {"inner": "data"}}),
            ("list_data", [1, 2, 3, "string", {"dict": "in_list"}]),
            ("number_data", 42),
            ("boolean_data", True),
        ]

        stored_data = {}

        def mock_setex(key, ttl, data):
            stored_data[key] = data
            return True

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.setex.side_effect = mock_setex
        mock_redis.get.side_effect = mock_get

        # Test storing and retrieving different data types
        for key, data in test_cases:
            await redis_client.set_temp_data(key, data)
            retrieved = await redis_client.get_temp_data(key)

            if isinstance(data, (dict, list)):
                # Should be JSON serialized
                assert retrieved == json.dumps(data)
            else:
                # Should be string
                assert retrieved == str(data)
