"""
End-to-end system integration tests.

These tests verify that the complete Actor Mesh E-commerce Support Agent system
works correctly from message input to final response, including all actors,
services, and data flow.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from actors.base import start_multiple_actors, stop_multiple_actors
from actors.context_retriever import ContextRetriever
from actors.execution_coordinator import ExecutionCoordinator
from actors.guardrail_validator import GuardrailValidator
from actors.intent_analyzer import IntentAnalyzer
from actors.response_generator import ResponseGenerator
from actors.sentiment_analyzer import SentimentAnalyzer
from models.message import MessagePayload, Route, StandardRoutes, create_support_message
from storage.redis_client import RedisClient

# Test environment configuration
TEST_ENV_CONFIG = {
    "NATS_URL": "nats://localhost:14222",
    "REDIS_URL": "redis://localhost:16379",
    "CUSTOMER_API_URL": "http://localhost:18001",
    "ORDERS_API_URL": "http://localhost:18002",
    "TRACKING_API_URL": "http://localhost:18003",
    "LOG_LEVEL": "INFO",
    "LITELLM_MODEL": "gpt-3.5-turbo",
    "SENTIMENT_CONFIDENCE_THRESHOLD": "0.7",
    "INTENT_TIMEOUT": "30",
    "RESPONSE_TEMPERATURE": "0.3",
    "USE_LLM_VALIDATION": "true",
}

# Helper functions for E2E tests
async def wait_for_actor_ready(actor, timeout: float = 10.0):
    """Wait for an actor to be ready for processing."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if hasattr(actor, '_running') and actor._running:
            await asyncio.sleep(0.5)
            return True
        await asyncio.sleep(0.1)
    return False

async def create_and_start_actor(actor_class, **kwargs):
    """Create and start an actor instance for E2E testing."""
    kwargs.setdefault('nats_url', TEST_ENV_CONFIG["NATS_URL"])
    actor = actor_class(**kwargs)
    await actor.start()
    ready = await wait_for_actor_ready(actor)
    if not ready:
        await actor.stop()
        raise RuntimeError(f"Actor {actor_class.__name__} failed to become ready")
    return actor

async def process_message_through_actors(message, actors, timeout: float = 30.0):
    """Process a message through a sequence of actors."""
    payload = message.payload
    start_time = time.time()

    for i, actor in enumerate(actors):
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Processing timeout at actor {i}: {actor.__class__.__name__}")
        try:
            result = await actor.process(payload)
            if result and hasattr(actor, '_enrich_payload'):
                await actor._enrich_payload(payload, result)
        except Exception as e:
            raise RuntimeError(f"Processing failed at actor {i} ({actor.__class__.__name__}): {e}")
    return payload


class TestSystemEndToEnd:
    """End-to-end system integration tests."""

    @pytest.fixture
    async def mock_infrastructure(self):
        """Set up mock infrastructure (NATS, Redis, APIs)."""
        # Mock NATS
        mock_nc = AsyncMock()
        mock_js = AsyncMock()
        mock_js.add_stream = AsyncMock()
        mock_js.stream_info = AsyncMock()
        mock_js.subscribe = AsyncMock()
        mock_js.publish = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_nc.close = AsyncMock()

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.close = AsyncMock()

        # Mock HTTP client for API calls
        mock_http_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock()

        # Configure API responses
        def configure_api_response(url):
            if "customers" in url:
                return {
                    "customer_id": "CUST-12345",
                    "profile": {
                        "first_name": "John",
                        "last_name": "Doe",
                        "email": "test@example.com",
                        "tier": "premium",
                    },
                }
            elif "orders" in url:
                return {
                    "orders": [
                        {
                            "order_id": "ORD-12345",
                            "status": "shipped",
                            "expected_delivery": "2024-01-15",
                            "items": [{"name": "Laptop", "quantity": 1, "price": 999.99}],
                        }
                    ]
                }
            elif "tracking" in url:
                return {"tracking_number": "TRK123456", "status": "in_transit", "estimated_delivery": "2024-01-15"}
            return {}

        mock_response.json.side_effect = lambda: configure_api_response(mock_http_client.get.call_args[0][0])
        mock_http_client.get.return_value = mock_response

        with (
            patch("nats.connect", return_value=mock_nc),
            patch("redis.asyncio.from_url", return_value=mock_redis),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client_class.return_value.__aenter__.return_value = mock_http_client

            yield {"nats": {"nc": mock_nc, "js": mock_js}, "redis": mock_redis, "http": mock_http_client}

    @pytest.fixture
    def mock_llm_responses(self):
        """Mock LLM API responses."""
        responses = {
            "intent_analysis": {
                "intent": {"category": "order_inquiry", "subcategory": "delivery_status"},
                "confidence": 0.87,
                "entities": [{"type": "order_id", "value": "ORD-12345"}, {"type": "emotion", "value": "frustrated"}],
                "reasoning": "Customer is asking about order delivery with emotional language",
            },
            "response_generation": {
                "response_text": "I sincerely apologize for the delay with your order ORD-12345. I understand your frustration, and I'm here to help resolve this immediately. Let me check the tracking details and provide you with an update.",
                "tone": "empathetic_professional",
                "key_points": ["Acknowledged frustration", "Apologized for delay", "Offered immediate assistance"],
                "confidence": 0.92,
            },
        }

        def mock_completion(*args, **kwargs):
            messages = kwargs.get("messages", [])
            last_message = messages[-1]["content"].lower() if messages else ""

            if "intent" in last_message or "analyze" in last_message:
                response_data = responses["intent_analysis"]
            else:
                response_data = responses["response_generation"]

            return MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(response_data)))])

        with patch("litellm.acompletion", side_effect=mock_completion):
            yield responses

    @pytest.mark.asyncio
    async def test_complete_support_flow_angry_customer(self, e2e_environment, healthy_services, clean_test_data, mock_llm_responses):
        """Test complete support flow for an angry customer scenario."""
        # Create message for angry customer
        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="I'm absolutely furious! My order ORD-12345 was supposed to arrive yesterday but it's still not here! This is completely unacceptable and I need this fixed RIGHT NOW!",
            customer_email="angry.customer@example.com",
            session_id="e2e-angry-test",
            route=route,
        )

        # Create and start all actors with real infrastructure
        actors = []
        try:
            # Create actors one by one to handle any startup issues
            sentiment_analyzer = await create_and_start_actor(SentimentAnalyzer)
            actors.append(sentiment_analyzer)

            intent_analyzer = await create_and_start_actor(IntentAnalyzer)
            actors.append(intent_analyzer)

            context_retriever = await create_and_start_actor(ContextRetriever)
            actors.append(context_retriever)

            response_generator = await create_and_start_actor(ResponseGenerator)
            actors.append(response_generator)

            guardrail_validator = await create_and_start_actor(GuardrailValidator)
            actors.append(guardrail_validator)

            execution_coordinator = await create_and_start_actor(ExecutionCoordinator)
            actors.append(execution_coordinator)

            # Process message through the complete flow
            final_payload = await process_message_through_actors(message, actors)

            # Verify sentiment analysis
            assert final_payload.sentiment is not None
            assert final_payload.sentiment["sentiment"]["label"] == "negative"
            assert final_payload.sentiment["urgency"]["level"] in ["medium", "high"]
            assert final_payload.sentiment["is_complaint"] is True

            # Verify intent analysis
            assert final_payload.intent is not None
            assert final_payload.intent["intent"]["category"] == "order_inquiry"
            assert final_payload.intent["confidence"] > 0.8

            # Verify context retrieval
            assert final_payload.context is not None
            assert "customer_context" in final_payload.context or "order_context" in final_payload.context

            # Verify response generation
            assert final_payload.response is not None
            assert len(final_payload.response) > 20

            # Verify complete message enrichment (check what's actually available)
            enrichments_found = sum([
                1 if final_payload.sentiment else 0,
                1 if final_payload.intent else 0,
                1 if final_payload.context else 0,
                1 if final_payload.response else 0,
                1 if hasattr(final_payload, 'guardrail_check') and final_payload.guardrail_check else 0,
                1 if hasattr(final_payload, 'execution_result') and final_payload.execution_result else 0,
            ])

            # Ensure at least the core enrichments are present
            assert enrichments_found >= 4, f"Expected at least 4 enrichments, got {enrichments_found}"

        except Exception as e:
            # Print debug info for troubleshooting
            print(f"Test failed with error: {e}")
            if actors:
                print(f"Actors created: {[actor.__class__.__name__ for actor in actors]}")
            raise
        finally:
            # Clean up actors
            for actor in actors:
                try:
                    await actor.stop()
                except Exception as cleanup_error:
                    print(f"Error stopping actor {actor.__class__.__name__}: {cleanup_error}")

    @pytest.mark.asyncio
    async def test_complete_support_flow_happy_customer(self, e2e_environment, healthy_services, clean_test_data, mock_llm_responses):
        """Test complete support flow for a happy customer scenario."""
        # Create message for happy customer
        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="Thank you so much for the excellent service! I just wanted to check the status of my order ORD-12345. Everything has been wonderful so far!",
            customer_email="happy.customer@example.com",
            session_id="e2e-happy-test",
            route=route,
        )

        # Create and start actors with real infrastructure
        actors = []
        try:
            # Create actors one by one
            sentiment_analyzer = await create_and_start_actor(SentimentAnalyzer)
            actors.append(sentiment_analyzer)

            intent_analyzer = await create_and_start_actor(IntentAnalyzer)
            actors.append(intent_analyzer)

            context_retriever = await create_and_start_actor(ContextRetriever)
            actors.append(context_retriever)

            response_generator = await create_and_start_actor(ResponseGenerator)
            actors.append(response_generator)

            # Process message through the flow
            final_payload = await process_message_through_actors(message, actors)

            # Verify positive sentiment detection
            assert final_payload.sentiment["sentiment"]["label"] == "positive"
            assert final_payload.sentiment["urgency"]["level"] == "low"
            assert final_payload.sentiment["is_complaint"] is False

            # Verify response is appropriate for positive sentiment
            assert final_payload.response is not None
            assert len(final_payload.response) > 20

        finally:
            # Clean up actors
            for actor in actors:
                try:
                    await actor.stop()
                except Exception as cleanup_error:
                    print(f"Error stopping actor {actor.__class__.__name__}: {cleanup_error}")

    @pytest.mark.asyncio
    async def test_system_performance_under_load(self, e2e_environment, healthy_services, clean_test_data, mock_llm_responses):
        """Test system performance under concurrent load."""
        # Create multiple test messages
        messages = []
        for i in range(10):
            route = Route(steps=["sentiment_analyzer"])
            message = create_support_message(
                customer_message=f"Test message {i} for performance testing",
                customer_email=f"perf-test-{i}@example.com",
                session_id=f"perf-test-{i}",
                route=route,
            )
            messages.append(message)

        # Create sentiment analyzer with real infrastructure
        analyzer = await create_and_start_actor(SentimentAnalyzer)

        try:
            # Measure concurrent processing time
            start_time = time.time()

            tasks = [analyzer.process(msg.payload) for msg in messages]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            end_time = time.time()
            processing_time = end_time - start_time

            # Verify all processed successfully
            assert len(results) == 10
            for result in results:
                assert not isinstance(result, Exception)
                assert result is not None

            # Verify reasonable performance (should handle 10 messages in under 5 seconds for real infrastructure)
            assert processing_time < 5.0

            # Calculate throughput
            throughput = len(messages) / processing_time
            assert throughput > 2  # Should process at least 2 messages per second with real infrastructure

        finally:
            await analyzer.stop()

    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, e2e_environment, clean_test_data):
        """Test system error recovery and resilience."""

        # Create an actor that will fail initially
        class FlakySentimentAnalyzer(SentimentAnalyzer):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.call_count = 0

            async def process(self, payload):
                self.call_count += 1
                if self.call_count <= 2:  # Fail first 2 calls
                    raise Exception("Simulated failure")
                return await super().process(payload)

        flaky_analyzer = await create_and_start_actor(FlakySentimentAnalyzer)

        try:
            message = create_support_message(
                customer_message="Test message for error recovery",
                customer_email="error-test@example.com",
                session_id="error-recovery-test",
                route=Route(steps=["sentiment_analyzer"]),
            )

            # First two calls should fail
            with pytest.raises(Exception, match="Simulated failure"):
                await flaky_analyzer.process(message.payload)

            with pytest.raises(Exception, match="Simulated failure"):
                await flaky_analyzer.process(message.payload)

            # Third call should succeed
            result = await flaky_analyzer.process(message.payload)
            assert result is not None
            assert "sentiment" in result

        finally:
            await flaky_analyzer.stop()

    @pytest.mark.asyncio
    async def test_data_persistence_and_session_management(self, e2e_environment, redis_client_e2e, clean_test_data):
        """Test data persistence and session management."""
        # Use the real Redis client from fixture
        redis_client = redis_client_e2e

        # Create a session
        session = await redis_client.create_session("e2e-session-test", "session-test@example.com")
        assert session.session_id == "e2e-session-test"
        assert session.customer_email == "session-test@example.com"

        # Update session with context
        context_data = {
            "customer_tier": "premium",
            "last_interaction": "2024-01-15T10:00:00",
            "issue_type": "order_inquiry",
        }
        await redis_client.set_context("session-test@example.com", context_data)

        # Retrieve context
        retrieved_context = await redis_client.get_context("session-test@example.com")
        assert retrieved_context == context_data

        # Increment message count
        count = await redis_client.increment_message_count("e2e-session-test")
        assert count == 1

        # Update session status
        success = await redis_client.update_session("e2e-session-test", status="resolved")
        assert success is True

    @pytest.mark.asyncio
    async def test_system_health_and_monitoring(self, e2e_environment, redis_client_e2e, clean_test_data):
        """Test system health checks and monitoring capabilities."""
        # Test actor health
        analyzer = await create_and_start_actor(SentimentAnalyzer)

        try:
            # Verify actor is running
            assert analyzer._running is True

            # Test basic functionality
            test_payload = MessagePayload(
                customer_message="Health check test message", customer_email="health@example.com"
            )

            result = await analyzer.process(test_payload)
            assert result is not None

        finally:
            await analyzer.stop()
            assert analyzer._running is False

        # Test Redis health (using the real Redis client from fixture)
        health = await redis_client_e2e.health_check()

        assert health["status"] == "healthy"
        assert health["test_passed"] is True

    @pytest.mark.asyncio
    async def test_message_routing_and_flow_control(self, e2e_environment, healthy_services, clean_test_data, mock_llm_responses):
        """Test message routing and flow control through the system."""
        # Create message with custom routing
        custom_route = Route(
            steps=["sentiment_analyzer", "intent_analyzer", "response_generator"], error_handler="escalation_router"
        )

        message = create_support_message(
            customer_message="I need help with my account settings",
            customer_email="routing-test@example.com",
            session_id="routing-flow-test",
            route=custom_route,
        )

        # Create actors for the custom route with real infrastructure
        actors = []
        try:
            sentiment_analyzer = await create_and_start_actor(SentimentAnalyzer)
            actors.append(sentiment_analyzer)

            intent_analyzer = await create_and_start_actor(IntentAnalyzer)
            actors.append(intent_analyzer)

            response_generator = await create_and_start_actor(ResponseGenerator)
            actors.append(response_generator)

            # Test route navigation
            assert message.route.get_current_actor() == "sentiment_analyzer"
            assert message.route.get_next_actor() == "intent_analyzer"
            assert not message.route.is_complete()

            # Advance through route
            assert message.route.advance() is True
            assert message.route.get_current_actor() == "intent_analyzer"

            assert message.route.advance() is True
            assert message.route.get_current_actor() == "response_generator"

            assert message.route.advance() is False  # At end
            assert message.route.is_complete()

        finally:
            # Clean up actors
            for actor in actors:
                try:
                    await actor.stop()
                except Exception as cleanup_error:
                    print(f"Error stopping actor {actor.__class__.__name__}: {cleanup_error}")

    @pytest.mark.asyncio
    async def test_end_to_end_response_quality(self, e2e_environment, healthy_services, clean_test_data, mock_llm_responses):
        """Test end-to-end response quality and appropriateness."""
        test_scenarios = [
            {
                "message": "I'm frustrated with the delayed delivery of order ORD-12345",
                "email": "frustrated@example.com",
                "expected_sentiment": "negative",
                "expected_urgency": ["medium", "high"],
                "expected_response_keywords": ["apologize", "understand", "delay"],
            },
            {
                "message": "Thank you for the excellent customer service!",
                "email": "satisfied@example.com",
                "expected_sentiment": "positive",
                "expected_urgency": ["low"],
                "expected_response_keywords": ["thank", "appreciate", "glad"],
            },
            {
                "message": "Can you help me track my recent order?",
                "email": "neutral@example.com",
                "expected_sentiment": "neutral",
                "expected_urgency": ["low", "medium"],
                "expected_response_keywords": ["help", "track", "order"],
            },
        ]

        # Create core actors with real infrastructure
        actors = []
        try:
            sentiment_analyzer = await create_and_start_actor(SentimentAnalyzer)
            actors.append(sentiment_analyzer)

            intent_analyzer = await create_and_start_actor(IntentAnalyzer)
            actors.append(intent_analyzer)

            response_generator = await create_and_start_actor(ResponseGenerator)
            actors.append(response_generator)

            for scenario in test_scenarios:
                # Create message for scenario
                route = Route(steps=["sentiment_analyzer", "intent_analyzer", "response_generator"])
                message = create_support_message(
                    customer_message=scenario["message"],
                    customer_email=scenario["email"],
                    session_id=f"quality-test-{hash(scenario['email'])}",
                    route=route,
                )

                # Process message through actors
                final_payload = await process_message_through_actors(message, actors)

                # Verify sentiment detection
                assert final_payload.sentiment["sentiment"]["label"] == scenario["expected_sentiment"]
                assert final_payload.sentiment["urgency"]["level"] in scenario["expected_urgency"]

                # Verify response quality
                assert final_payload.response is not None
                assert len(final_payload.response) > 20  # Meaningful response length

                # Check for expected keywords in response (case-insensitive)
                response_lower = final_payload.response.lower()
                keyword_found = any(keyword in response_lower for keyword in scenario["expected_response_keywords"])
                assert keyword_found, (
                    f"None of {scenario['expected_response_keywords']} found in response: {final_payload.response}"
                )

        finally:
            # Clean up actors
            for actor in actors:
                try:
                    await actor.stop()
                except Exception as cleanup_error:
                    print(f"Error stopping actor {actor.__class__.__name__}: {cleanup_error}")
