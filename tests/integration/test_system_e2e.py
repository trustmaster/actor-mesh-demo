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
from actors.base import start_multiple_actors, stop_multiple_actors
from actors.context_retriever import ContextRetriever
from actors.execution_coordinator import ExecutionCoordinator
from actors.guardrail_validator import GuardrailValidator
from actors.intent_analyzer import IntentAnalyzer
from actors.response_generator import ResponseGenerator
from actors.sentiment_analyzer import SentimentAnalyzer
from models.message import StandardRoutes, create_support_message
from storage.redis_client import RedisClient


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
    async def test_complete_support_flow_angry_customer(self, mock_infrastructure, mock_llm_responses):
        """Test complete support flow for an angry customer scenario."""
        # Create message for angry customer
        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="I'm absolutely furious! My order ORD-12345 was supposed to arrive yesterday but it's still not here! This is completely unacceptable and I need this fixed RIGHT NOW!",
            customer_email="angry.customer@example.com",
            session_id="e2e-angry-test",
            route=route,
        )

        # Create all actors
        actors = [
            SentimentAnalyzer(),
            IntentAnalyzer(),
            ContextRetriever(),
            ResponseGenerator(),
            GuardrailValidator(),
            ExecutionCoordinator(),
        ]

        try:
            # Start all actors
            await start_multiple_actors(actors)

            # Process through the complete flow
            payload = message.payload

            # 1. Sentiment Analysis
            sentiment_result = await actors[0].process(payload)
            await actors[0]._enrich_payload(payload, sentiment_result)

            # Verify sentiment analysis
            assert payload.sentiment is not None
            assert payload.sentiment["sentiment"]["label"] == "negative"
            assert payload.sentiment["urgency"]["level"] in ["medium", "high"]
            assert payload.sentiment["is_complaint"] is True

            # 2. Intent Analysis
            intent_result = await actors[1].process(payload)
            await actors[1]._enrich_payload(payload, intent_result)

            # Verify intent analysis
            assert payload.intent is not None
            assert payload.intent["intent"]["category"] == "order_inquiry"
            assert payload.intent["confidence"] > 0.8

            # 3. Context Retrieval
            context_result = await actors[2].process(payload)
            await actors[2]._enrich_payload(payload, context_result)

            # Verify context retrieval
            assert payload.context is not None
            assert "customer_context" in payload.context
            assert "order_context" in payload.context

            # 4. Response Generation
            response_result = await actors[3].process(payload)
            await actors[3]._enrich_payload(payload, response_result)

            # Verify response generation
            assert payload.response is not None
            assert len(payload.response) > 50
            assert "apologize" in payload.response.lower()

            # 5. Guardrail Validation
            guardrail_result = await actors[4].process(payload)
            await actors[4]._enrich_payload(payload, guardrail_result)

            # Verify guardrail validation
            assert payload.guardrail_check is not None
            assert "approved" in payload.guardrail_check
            assert "validation_status" in payload.guardrail_check

            # 6. Execution Coordination
            execution_result = await actors[5].process(payload)
            await actors[5]._enrich_payload(payload, execution_result)

            # Verify execution coordination
            assert payload.execution_result is not None
            assert "execution_status" in payload.execution_result

            # Verify complete message enrichment
            assert all(
                [
                    payload.sentiment,
                    payload.intent,
                    payload.context,
                    payload.response,
                    payload.guardrail_check,
                    payload.execution_result,
                ]
            )

        finally:
            # Clean up
            await stop_multiple_actors(actors)

    @pytest.mark.asyncio
    async def test_complete_support_flow_happy_customer(self, mock_infrastructure, mock_llm_responses):
        """Test complete support flow for a happy customer scenario."""
        # Create message for happy customer
        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="Thank you so much for the excellent service! I just wanted to check the status of my order ORD-12345. Everything has been wonderful so far!",
            customer_email="happy.customer@example.com",
            session_id="e2e-happy-test",
            route=route,
        )

        # Create key actors for the flow
        actors = [SentimentAnalyzer(), IntentAnalyzer(), ContextRetriever(), ResponseGenerator()]

        try:
            await start_multiple_actors(actors)

            payload = message.payload

            # Process through sentiment and intent analysis
            sentiment_result = await actors[0].process(payload)
            await actors[0]._enrich_payload(payload, sentiment_result)

            intent_result = await actors[1].process(payload)
            await actors[1]._enrich_payload(payload, intent_result)

            context_result = await actors[2].process(payload)
            await actors[2]._enrich_payload(payload, context_result)

            response_result = await actors[3].process(payload)
            await actors[3]._enrich_payload(payload, response_result)

            # Verify positive sentiment detection
            assert payload.sentiment["sentiment"]["label"] == "positive"
            assert payload.sentiment["urgency"]["level"] == "low"
            assert payload.sentiment["is_complaint"] is False

            # Verify response is appropriate for positive sentiment
            assert payload.response is not None
            assert len(payload.response) > 20

        finally:
            await stop_multiple_actors(actors)

    @pytest.mark.asyncio
    async def test_system_performance_under_load(self, mock_infrastructure, mock_llm_responses):
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

        # Create sentiment analyzer
        analyzer = SentimentAnalyzer()
        await analyzer.start()

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

            # Verify reasonable performance (should handle 10 messages in under 2 seconds)
            assert processing_time < 2.0

            # Calculate throughput
            throughput = len(messages) / processing_time
            assert throughput > 5  # Should process at least 5 messages per second

        finally:
            await analyzer.stop()

    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, mock_infrastructure):
        """Test system error recovery and resilience."""

        # Create an actor that will fail initially
        class FlakySentimentAnalyzer(SentimentAnalyzer):
            def __init__(self):
                super().__init__()
                self.call_count = 0

            async def process(self, payload):
                self.call_count += 1
                if self.call_count <= 2:  # Fail first 2 calls
                    raise Exception("Simulated failure")
                return await super().process(payload)

        flaky_analyzer = FlakySentimentAnalyzer()
        await flaky_analyzer.start()

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
    async def test_data_persistence_and_session_management(self, mock_infrastructure):
        """Test data persistence and session management."""
        # Create Redis client for session management
        redis_client = RedisClient()

        try:
            await redis_client.connect()

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

        finally:
            await redis_client.disconnect()

    @pytest.mark.asyncio
    async def test_system_health_and_monitoring(self, mock_infrastructure):
        """Test system health checks and monitoring capabilities."""
        # Test actor health
        analyzer = SentimentAnalyzer()
        await analyzer.start()

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

        # Test Redis health
        redis_client = RedisClient()
        try:
            await redis_client.connect()
            health = await redis_client.health_check()

            assert health["status"] == "healthy"
            assert health["test_passed"] is True

        finally:
            await redis_client.disconnect()

    @pytest.mark.asyncio
    async def test_message_routing_and_flow_control(self, mock_infrastructure, mock_llm_responses):
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

        # Create actors for the route
        actors = [SentimentAnalyzer(), IntentAnalyzer(), ResponseGenerator()]

        try:
            await start_multiple_actors(actors)

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
            await stop_multiple_actors(actors)

    @pytest.mark.asyncio
    async def test_end_to_end_response_quality(self, mock_infrastructure, mock_llm_responses):
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

        # Create core actors
        actors = [SentimentAnalyzer(), IntentAnalyzer(), ResponseGenerator()]

        try:
            await start_multiple_actors(actors)

            for scenario in test_scenarios:
                # Create message for scenario
                route = Route(steps=["sentiment_analyzer", "intent_analyzer", "response_generator"])
                message = create_support_message(
                    customer_message=scenario["message"],
                    customer_email=scenario["email"],
                    session_id=f"quality-test-{hash(scenario['email'])}",
                    route=route,
                )

                payload = message.payload

                # Process through actors
                sentiment_result = await actors[0].process(payload)
                await actors[0]._enrich_payload(payload, sentiment_result)

                intent_result = await actors[1].process(payload)
                await actors[1]._enrich_payload(payload, intent_result)

                response_result = await actors[2].process(payload)
                await actors[2]._enrich_payload(payload, response_result)

                # Verify sentiment detection
                assert payload.sentiment["sentiment"]["label"] == scenario["expected_sentiment"]
                assert payload.sentiment["urgency"]["level"] in scenario["expected_urgency"]

                # Verify response quality
                assert payload.response is not None
                assert len(payload.response) > 20  # Meaningful response length

                # Check for expected keywords in response (case-insensitive)
                response_lower = payload.response.lower()
                keyword_found = any(keyword in response_lower for keyword in scenario["expected_response_keywords"])
                assert keyword_found, (
                    f"None of {scenario['expected_response_keywords']} found in response: {payload.response}"
                )

        finally:
            await stop_multiple_actors(actors)
