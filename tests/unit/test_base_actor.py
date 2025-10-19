"""
Unit tests for base actor classes.

Tests the core actor framework including BaseActor, ProcessorActor, RouterActor,
and utility functions for actor management.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from actors.base import (
    BaseActor,
    ProcessorActor,
    RouterActor,
    run_actors_forever,
    start_multiple_actors,
    stop_multiple_actors,
)
from models.message import Message, MessagePayload


class MockProcessorActor(ProcessorActor):
    """Test implementation of ProcessorActor."""

    def __init__(self, name: str = "test_processor", nats_url: str = "nats://localhost:4222"):
        super().__init__(name, nats_url)
        self.process_calls = []
        self.process_result = {"test": "result"}
        self.process_exception = None

    async def process(self, payload: MessagePayload):
        """Mock process method that records calls."""
        self.process_calls.append(payload)
        if self.process_exception:
            raise self.process_exception
        return self.process_result

    async def _enrich_payload(self, payload: MessagePayload, result):
        """Mock enrichment method."""
        payload.sentiment = result


class MockRouterActor(RouterActor):
    """Test implementation of RouterActor."""

    def __init__(self, name: str = "test_router", nats_url: str = "nats://localhost:4222"):
        super().__init__(name, nats_url)
        self.route_calls = []
        self.route_exception = None

    async def process(self, payload: MessagePayload):
        """Router process method."""
        return {"routing": "decision"}

    async def route_message(self, message: Message):
        """Mock route message method."""
        self.route_calls.append(message)
        if self.route_exception:
            raise self.route_exception


@pytest.fixture
def mock_nats_setup(mock_nats_connection, mock_jetstream):
    """Setup mocked NATS connection."""
    with patch("nats.connect") as mock_connect:
        mock_connect.return_value = mock_nats_connection
        mock_nats_connection.jetstream = MagicMock(return_value=mock_jetstream)
        yield mock_connect, mock_nats_connection, mock_jetstream


class TestBaseActor:
    """Test cases for BaseActor class."""

    def test_actor_initialization(self):
        """Test actor initialization."""
        actor = MockProcessorActor(name="test_actor", nats_url="nats://test:4222")

        assert actor.name == "test_actor"
        assert actor.nats_url == "nats://test:4222"
        assert actor.subject == "ecommerce.support.test_actor"
        assert actor.max_retries == 3
        assert actor.retry_delay == 1.0
        assert actor.processing_timeout == 30.0
        assert actor._running is False
        assert len(actor._tasks) == 0

    def test_actor_default_values(self):
        """Test actor with default values."""
        actor = MockProcessorActor()

        assert actor.nats_url == "nats://localhost:4222"
        assert actor.subject == "ecommerce.support.test_processor"

    @pytest.mark.asyncio
    async def test_actor_start_success(self, mock_nats_setup):
        """Test successful actor startup."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        await actor.start()

        assert actor._running is True
        assert actor.nc == mock_nc
        assert actor.js == mock_js
        mock_connect.assert_called_once_with("nats://localhost:4222")
        mock_js.stream_info.assert_called_once_with("ECOMMERCE_SUPPORT")
        mock_js.subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_actor_start_creates_stream(self, mock_nats_setup):
        """Test actor startup creates stream when it doesn't exist."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        # Simulate stream doesn't exist
        mock_js.stream_info.side_effect = Exception("Stream not found")

        actor = MockProcessorActor()
        await actor.start()

        mock_js.add_stream.assert_called_once_with(
            name="ECOMMERCE_SUPPORT",
            subjects=["ecommerce.support.*"],
            retention="workqueue",
            max_age=3600,
        )

    @pytest.mark.asyncio
    async def test_actor_start_failure(self, mock_nats_setup):
        """Test actor startup failure."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        mock_connect.side_effect = Exception("Connection failed")

        actor = MockProcessorActor()

        with pytest.raises(Exception, match="Connection failed"):
            await actor.start()

        assert actor._running is False

    @pytest.mark.asyncio
    async def test_actor_stop(self, mock_nats_setup):
        """Test actor stop functionality."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        await actor.start()
        assert actor._running is True

        await actor.stop()
        assert actor._running is False
        mock_nc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_actor_stop_not_running(self):
        """Test stopping actor that's not running."""
        actor = MockProcessorActor()

        # Should not raise exception
        await actor.stop()
        assert actor._running is False

    @pytest.mark.asyncio
    async def test_double_start_warning(self, mock_nats_setup):
        """Test starting actor twice shows warning."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        await actor.start()
        assert actor._running is True

        # Start again - should log warning but not fail
        with patch.object(actor.logger, "warning") as mock_warning:
            await actor.start()
            mock_warning.assert_called_once_with("Actor already running")

    @pytest.mark.asyncio
    async def test_process_message_success(self, mock_nats_setup, sample_message):
        """Test successful message processing."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        # Setup message
        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0

        # Create mock NATS message
        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Verify processing occurred
        assert len(actor.process_calls) == 1
        # Check core payload fields (payload gets enriched during processing)
        processed_payload = actor.process_calls[0]
        assert processed_payload.customer_message == sample_message.payload.customer_message
        assert processed_payload.customer_email == sample_message.payload.customer_email
        mock_msg.ack.assert_called_once()
        mock_msg.nak.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_wrong_actor(self, mock_nats_setup, sample_message):
        """Test message processing for wrong actor."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor(name="wrong_actor")

        # Message is for different actor
        sample_message.route.steps = ["correct_actor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should NAK the message
        assert len(actor.process_calls) == 0
        mock_msg.nak.assert_called_once()
        mock_msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_timeout(self, mock_nats_setup, sample_message):
        """Test message processing timeout."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()
        actor.processing_timeout = 0.01  # Very short timeout

        # Make process method slow
        async def slow_process(payload):
            await asyncio.sleep(0.1)  # Longer than timeout
            return {"result": "slow"}

        actor.process = slow_process

        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should handle timeout error
        mock_msg.nak.assert_called_once()
        mock_msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_exception(self, mock_nats_setup, sample_message):
        """Test message processing with exception."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()
        actor.process_exception = ValueError("Test exception")

        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should handle processing error
        mock_msg.nak.assert_called_once()
        mock_msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_message_routing_advance(self, mock_nats_setup, sample_message):
        """Test message routing to next actor."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        # Setup multi-step route
        sample_message.route.steps = ["test_processor", "next_actor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should publish to next actor
        expected_subject = "ecommerce.support.next_actor"
        mock_js.publish.assert_called_once()
        call_args = mock_js.publish.call_args[0]
        assert call_args[0] == expected_subject

    @pytest.mark.asyncio
    async def test_message_routing_complete(self, mock_nats_setup, sample_message):
        """Test message routing completion."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        # Setup single-step route (will be complete after processing)
        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should not publish anywhere (route complete)
        mock_js.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_handling_with_retries(self, mock_nats_setup, sample_message):
        """Test error handling with retry logic."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()
        actor.max_retries = 2
        actor.retry_delay = 0.01  # Fast retry for testing
        actor.process_exception = ValueError("Retry test")

        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0
        sample_message.metadata["retry_count"] = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should NAK for retry (not at max retries yet)
        mock_msg.nak.assert_called_once()
        mock_msg.ack.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_handling_max_retries(self, mock_nats_setup, sample_message):
        """Test error handling when max retries exceeded."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()
        actor.max_retries = 2
        actor.process_exception = ValueError("Max retry test")

        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0
        sample_message.route.error_handler = "error_handler"
        sample_message.metadata["retry_count"] = 3  # Already at max retries

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should route to error handler and ACK
        mock_js.publish.assert_called_once()
        call_args = mock_js.publish.call_args[0]
        assert call_args[0] == "ecommerce.support.error_handler"
        mock_msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message(self, mock_nats_setup, sample_message):
        """Test sending message to specific subject."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        await actor.start()
        await actor.send_message("test.subject", sample_message)

        mock_js.publish.assert_called_once_with("test.subject", json.dumps(sample_message.model_dump()).encode())

    @pytest.mark.asyncio
    async def test_send_message_not_started(self, sample_message):
        """Test sending message when actor not started."""
        actor = MockProcessorActor()

        with pytest.raises(RuntimeError, match="Actor not started"):
            await actor.send_message("test.subject", sample_message)

    def test_actor_repr(self):
        """Test actor string representation."""
        actor = MockProcessorActor(name="test_actor")

        repr_str = repr(actor)
        assert "MockProcessorActor" in repr_str
        assert "test_actor" in repr_str
        assert "running=False" in repr_str


class TestProcessorActor:
    """Test cases for ProcessorActor class."""

    def test_processor_actor_inheritance(self):
        """Test ProcessorActor inherits from BaseActor."""
        actor = MockProcessorActor()
        assert isinstance(actor, BaseActor)
        assert isinstance(actor, ProcessorActor)

    def test_processor_actor_initialization(self):
        """Test ProcessorActor initialization."""
        actor = MockProcessorActor(name="processor_test", nats_url="nats://test:4222")

        assert actor.name == "processor_test"
        assert actor.nats_url == "nats://test:4222"


class TestRouterActor:
    """Test cases for RouterActor class."""

    def test_router_actor_inheritance(self):
        """Test RouterActor inherits from BaseActor."""
        actor = MockRouterActor()
        assert isinstance(actor, BaseActor)
        assert isinstance(actor, RouterActor)

    @pytest.mark.asyncio
    async def test_router_custom_routing(self, mock_nats_setup, sample_message):
        """Test router actor custom routing logic."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        router = MockRouterActor()

        sample_message.route.steps = ["test_router"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()

        await router.start()
        await router._process_message(mock_msg)

        # Should call route_message instead of standard routing
        assert len(router.route_calls) == 1
        assert router.route_calls[0] == sample_message

    @pytest.mark.asyncio
    async def test_router_routing_exception(self, mock_nats_setup, sample_message):
        """Test router actor routing exception."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        router = MockRouterActor()
        router.route_exception = ValueError("Routing failed")

        sample_message.route.steps = ["test_router"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await router.start()
        await router._process_message(mock_msg)

        # Should handle routing error
        mock_msg.nak.assert_called_once()


class TestActorUtilities:
    """Test cases for actor utility functions."""

    @pytest.mark.asyncio
    async def test_start_multiple_actors(self, mock_nats_setup):
        """Test starting multiple actors concurrently."""
        mock_connect, mock_nc, mock_js = mock_nats_setup

        actors = [
            MockProcessorActor(name="actor1"),
            MockProcessorActor(name="actor2"),
            MockProcessorActor(name="actor3"),
        ]

        await start_multiple_actors(actors)

        for actor in actors:
            assert actor._running is True

    @pytest.mark.asyncio
    async def test_stop_multiple_actors(self, mock_nats_setup):
        """Test stopping multiple actors concurrently."""
        mock_connect, mock_nc, mock_js = mock_nats_setup

        actors = [
            MockProcessorActor(name="actor1"),
            MockProcessorActor(name="actor2"),
            MockProcessorActor(name="actor3"),
        ]

        # Start them first
        await start_multiple_actors(actors)

        # Then stop them
        await stop_multiple_actors(actors)

        for actor in actors:
            assert actor._running is False

    @pytest.mark.asyncio
    async def test_run_actors_forever_keyboard_interrupt(self, mock_nats_setup):
        """Test run_actors_forever with keyboard interrupt."""
        mock_connect, mock_nc, mock_js = mock_nats_setup

        actors = [MockProcessorActor(name="actor1")]

        # Mock keyboard interrupt after short delay
        call_count = 0
        async def interrupt_after_delay(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:  # Interrupt on second call
                raise KeyboardInterrupt()
            await asyncio.sleep(0.01)  # Small delay to avoid tight loop

        with patch("asyncio.sleep", side_effect=interrupt_after_delay):
            await run_actors_forever(actors)

        # Should have stopped the actors
        assert actors[0]._running is False

    @pytest.mark.asyncio
    async def test_run_actors_forever_exception(self, mock_nats_setup):
        """Test run_actors_forever with startup exception."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        mock_connect.side_effect = Exception("Startup failed")

        actors = [MockProcessorActor(name="actor1")]

        with pytest.raises(Exception, match="Startup failed"):
            await run_actors_forever(actors)


class TestActorTaskManagement:
    """Test cases for actor task management."""

    @pytest.mark.asyncio
    async def test_task_cleanup_on_completion(self, mock_nats_setup, sample_message):
        """Test that completed tasks are cleaned up."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        sample_message.route.steps = ["test_processor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()

        await actor.start()

        initial_task_count = len(actor._tasks)
        await actor._handle_message_wrapper(mock_msg)

        # Wait for task to complete
        await asyncio.sleep(0.1)

        # Task should be cleaned up
        assert len(actor._tasks) == initial_task_count

    @pytest.mark.asyncio
    async def test_task_cancellation_on_stop(self, mock_nats_setup):
        """Test that tasks are cancelled when actor stops."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        await actor.start()

        # Create a long-running task
        async def long_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(long_task())
        actor._tasks.add(task)

        # Stop the actor
        await actor.stop()

        # Task should be cancelled
        assert task.cancelled()


class TestActorErrorScenarios:
    """Test cases for various error scenarios."""

    @pytest.mark.asyncio
    async def test_malformed_message_data(self, mock_nats_setup):
        """Test handling of malformed message data."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        actor = MockProcessorActor()

        mock_msg = MagicMock()
        mock_msg.data = b"invalid json data"
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should NAK malformed message
        mock_msg.nak.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_creation_failure(self, mock_nats_setup):
        """Test handling of stream creation failure."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        # Stream doesn't exist and creation fails
        mock_js.stream_info.side_effect = Exception("Stream not found")
        mock_js.add_stream.side_effect = Exception("Stream creation failed")

        actor = MockProcessorActor()

        # Should raise exception on stream creation failure
        with pytest.raises(Exception, match="Stream creation failed"):
            await actor.start()

    @pytest.mark.asyncio
    async def test_subscription_failure(self, mock_nats_setup):
        """Test handling of subscription failure."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        mock_js.subscribe.side_effect = Exception("Subscription failed")

        actor = MockProcessorActor()

        # Should raise exception on subscription failure
        with pytest.raises(Exception, match="Subscription failed"):
            await actor.start()

    @pytest.mark.asyncio
    async def test_publish_failure_during_routing(self, mock_nats_setup, sample_message):
        """Test handling of publish failure during message routing."""
        mock_connect, mock_nc, mock_js = mock_nats_setup
        mock_js.publish.side_effect = Exception("Publish failed")

        actor = MockProcessorActor()

        sample_message.route.steps = ["test_processor", "next_actor"]
        sample_message.route.current_step = 0

        mock_msg = MagicMock()
        mock_msg.data = json.dumps(sample_message.model_dump()).encode()
        mock_msg.ack = AsyncMock()
        mock_msg.nak = AsyncMock()

        await actor.start()
        await actor._process_message(mock_msg)

        # Should still try to route despite publish failure
        mock_js.publish.assert_called_once()
