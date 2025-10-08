"""
Unit tests for message models.

Tests the core message protocol models including MessagePayload, Route, Message,
StandardRoutes, and factory functions.
"""

from datetime import datetime

from models.message import (
    Message,
    MessagePayload,
    Route,
    StandardRoutes,
    create_error_message,
    create_support_message,
)


class TestMessagePayload:
    """Test cases for MessagePayload model."""

    def test_create_basic_payload(self):
        """Test creating a basic message payload."""
        payload = MessagePayload(customer_message="Hello, I need help", customer_email="test@example.com")

        assert payload.customer_message == "Hello, I need help"
        assert payload.customer_email == "test@example.com"
        assert payload.sentiment is None
        assert payload.intent is None
        assert payload.context is None
        assert payload.response is None
        assert payload.error is None
        assert payload.recovery_log == []

    def test_payload_enrichment(self):
        """Test adding enrichments to payload."""
        payload = MessagePayload(customer_message="I'm angry about my order!", customer_email="angry@example.com")

        # Add sentiment enrichment
        sentiment_data = {"sentiment": {"label": "negative", "score": -0.8}, "urgency": {"level": "high", "score": 0.9}}
        payload.sentiment = sentiment_data

        # Add intent enrichment
        intent_data = {"intent": {"category": "complaint", "subcategory": "order_issue"}, "confidence": 0.85}
        payload.intent = intent_data

        assert payload.sentiment == sentiment_data
        assert payload.intent == intent_data
        assert payload.sentiment["sentiment"]["label"] == "negative"
        assert payload.intent["confidence"] == 0.85

    def test_payload_serialization(self):
        """Test payload serialization and deserialization."""
        original = MessagePayload(
            customer_message="Test message",
            customer_email="test@example.com",
            sentiment={"label": "positive"},
            intent={"category": "inquiry"},
        )

        # Convert to dict and back
        payload_dict = original.dict()
        reconstructed = MessagePayload(**payload_dict)

        assert reconstructed.customer_message == original.customer_message
        assert reconstructed.customer_email == original.customer_email
        assert reconstructed.sentiment == original.sentiment
        assert reconstructed.intent == original.intent

    def test_payload_with_error(self):
        """Test payload with error information."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")

        error_info = {
            "type": "processing_error",
            "message": "Failed to process",
            "actor": "test_actor",
            "timestamp": datetime.utcnow().isoformat(),
        }
        payload.error = error_info
        payload.recovery_log.append(error_info)

        assert payload.error == error_info
        assert len(payload.recovery_log) == 1
        assert payload.recovery_log[0]["type"] == "processing_error"


class TestRoute:
    """Test cases for Route model."""

    def test_create_basic_route(self):
        """Test creating a basic route."""
        route = Route(steps=["actor1", "actor2", "actor3"], current_step=0, error_handler="error_actor")

        assert route.steps == ["actor1", "actor2", "actor3"]
        assert route.current_step == 0
        assert route.error_handler == "error_actor"

    def test_route_navigation(self):
        """Test route navigation methods."""
        route = Route(steps=["actor1", "actor2", "actor3"])

        # Test initial state
        assert route.get_current_actor() == "actor1"
        assert route.get_next_actor() == "actor2"
        assert not route.is_complete()

        # Advance to next step
        assert route.advance() is True
        assert route.current_step == 1
        assert route.get_current_actor() == "actor2"
        assert route.get_next_actor() == "actor3"
        assert not route.is_complete()

        # Advance to final step
        assert route.advance() is True
        assert route.current_step == 2
        assert route.get_current_actor() == "actor3"
        assert route.get_next_actor() is None
        assert route.is_complete()

        # Try to advance past end
        assert route.advance() is False
        assert route.current_step == 2

    def test_empty_route(self):
        """Test route with no steps."""
        route = Route(steps=[])

        assert route.get_current_actor() is None
        assert route.get_next_actor() is None
        assert route.is_complete()  # Empty route is complete
        assert route.advance() is False

    def test_single_step_route(self):
        """Test route with single step."""
        route = Route(steps=["only_actor"])

        assert route.get_current_actor() == "only_actor"
        assert route.get_next_actor() is None
        assert route.is_complete()
        assert route.advance() is False

    def test_route_with_mid_position(self):
        """Test route starting from middle position."""
        route = Route(steps=["actor1", "actor2", "actor3"], current_step=1)

        assert route.get_current_actor() == "actor2"
        assert route.get_next_actor() == "actor3"
        assert not route.is_complete()


class TestMessage:
    """Test cases for Message model."""

    def test_create_basic_message(self):
        """Test creating a basic message."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1", "actor2"])

        message = Message(session_id="test-session", route=route, payload=payload)

        assert message.session_id == "test-session"
        assert message.route == route
        assert message.payload == payload
        assert isinstance(message.message_id, str)
        assert len(message.message_id) > 0
        assert "created_at" in message.metadata
        assert message.metadata["retry_count"] == 0

    def test_message_with_custom_id(self):
        """Test creating message with custom ID."""
        custom_id = "custom-message-id"
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1"])

        message = Message(message_id=custom_id, session_id="test-session", route=route, payload=payload)

        assert message.message_id == custom_id

    def test_message_enrichment(self):
        """Test message enrichment functionality."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1"])
        message = Message(session_id="test-session", route=route, payload=payload)

        # Test enrichment
        sentiment_data = {"label": "positive", "score": 0.8}
        message.add_enrichment("sentiment", sentiment_data)

        assert message.payload.sentiment == sentiment_data

    def test_message_error_handling(self):
        """Test message error handling functionality."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1"])
        message = Message(session_id="test-session", route=route, payload=payload)

        # Add error
        message.add_error("processing_error", "Test error", "test_actor")

        assert message.payload.error is not None
        assert message.payload.error["type"] == "processing_error"
        assert message.payload.error["message"] == "Test error"
        assert message.payload.error["actor"] == "test_actor"
        assert "timestamp" in message.payload.error

        # Check recovery log
        assert len(message.payload.recovery_log) == 1
        assert message.payload.recovery_log[0] == message.payload.error

    def test_message_retry_increment(self):
        """Test retry counter functionality."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1"])
        message = Message(session_id="test-session", route=route, payload=payload)

        # Initial state
        assert message.metadata["retry_count"] == 0
        assert "last_retry_at" not in message.metadata

        # Increment retry
        message.increment_retry()
        assert message.metadata["retry_count"] == 1
        assert "last_retry_at" in message.metadata

        # Increment again
        message.increment_retry()
        assert message.metadata["retry_count"] == 2

    def test_nats_subject_generation(self):
        """Test NATS subject generation."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1"])
        message = Message(session_id="test-session", route=route, payload=payload)

        subject = message.to_nats_subject("test_actor")
        assert subject == "ecommerce.support.test_actor"

    def test_message_metadata(self):
        """Test message metadata functionality."""
        payload = MessagePayload(customer_message="Test message", customer_email="test@example.com")
        route = Route(steps=["actor1"])

        custom_metadata = {"priority": "high", "source": "web_chat"}

        message = Message(session_id="test-session", route=route, payload=payload, metadata=custom_metadata)

        assert message.metadata["priority"] == "high"
        assert message.metadata["source"] == "web_chat"
        assert "created_at" in message.metadata  # Should be added automatically
        assert "retry_count" in message.metadata  # Should be added automatically


class TestStandardRoutes:
    """Test cases for StandardRoutes factory methods."""

    def test_complaint_analysis_route(self):
        """Test complaint analysis route."""
        route = StandardRoutes.complaint_analysis_route()

        expected_steps = ["sentiment_analyzer", "intent_analyzer", "context_retriever", "decision_router"]
        assert route.steps == expected_steps
        assert route.error_handler == "escalation_router"
        assert route.current_step == 0

    def test_response_generation_route(self):
        """Test response generation route."""
        route = StandardRoutes.response_generation_route()

        expected_steps = ["response_generator", "guardrail_validator", "response_aggregator"]
        assert route.steps == expected_steps
        assert route.error_handler == "escalation_router"
        assert route.current_step == 0

    def test_action_execution_route(self):
        """Test action execution route."""
        route = StandardRoutes.action_execution_route()

        expected_steps = ["execution_coordinator", "response_aggregator"]
        assert route.steps == expected_steps
        assert route.error_handler == "escalation_router"
        assert route.current_step == 0

    def test_full_support_flow(self):
        """Test full support flow route."""
        route = StandardRoutes.full_support_flow()

        expected_steps = [
            "sentiment_analyzer",
            "intent_analyzer",
            "context_retriever",
            "decision_router",
            "response_generator",
            "guardrail_validator",
            "response_aggregator",
        ]
        assert route.steps == expected_steps
        assert route.error_handler == "escalation_router"
        assert route.current_step == 0

    def test_standard_routes_immutability(self):
        """Test that standard routes are independent instances."""
        route1 = StandardRoutes.full_support_flow()
        route2 = StandardRoutes.full_support_flow()

        # Should be separate instances
        assert route1 is not route2

        # Modifying one shouldn't affect the other
        route1.advance()
        assert route1.current_step == 1
        assert route2.current_step == 0


class TestMessageFactories:
    """Test cases for message factory functions."""

    def test_create_support_message(self):
        """Test create_support_message factory."""
        route = Route(steps=["actor1", "actor2"])

        message = create_support_message(
            customer_message="I need help",
            customer_email="customer@example.com",
            session_id="test-session",
            route=route,
        )

        assert isinstance(message, Message)
        assert message.session_id == "test-session"
        assert message.route == route
        assert message.payload.customer_message == "I need help"
        assert message.payload.customer_email == "customer@example.com"
        assert isinstance(message.message_id, str)

    def test_create_error_message(self):
        """Test create_error_message factory."""
        # Create original message
        original_payload = MessagePayload(customer_message="Original message", customer_email="original@example.com")
        original_route = Route(steps=["actor1", "actor2"], error_handler="error_handler")
        original_message = Message(session_id="original-session", route=original_route, payload=original_payload)

        # Create error message
        error_message = create_error_message(
            original_message=original_message,
            error_type="timeout",
            error_message="Processing timeout",
            actor="failing_actor",
        )

        assert isinstance(error_message, Message)
        assert error_message.session_id == "original-session"
        assert error_message.route.steps == ["error_handler"]
        assert error_message.route.current_step == 0
        assert error_message.payload == original_payload

        # Check error information
        assert error_message.payload.error is not None
        assert error_message.payload.error["type"] == "timeout"
        assert error_message.payload.error["message"] == "Processing timeout"
        assert error_message.payload.error["actor"] == "failing_actor"
        assert len(error_message.payload.recovery_log) == 1

    def test_create_error_message_no_error_handler(self):
        """Test create_error_message when original has no error handler."""
        # Create original message without error handler
        original_payload = MessagePayload(customer_message="Original message", customer_email="original@example.com")
        original_route = Route(steps=["actor1", "actor2"])  # No error_handler
        original_message = Message(session_id="original-session", route=original_route, payload=original_payload)

        # Create error message
        error_message = create_error_message(
            original_message=original_message,
            error_type="processing_error",
            error_message="Failed to process",
            actor="failing_actor",
        )

        # Should default to escalation_router
        assert error_message.route.steps == ["escalation_router"]


class TestMessageIntegration:
    """Integration tests for message components working together."""

    def test_message_flow_simulation(self):
        """Test simulating a message flowing through actors."""
        # Create message with full support flow
        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="I'm upset about my delayed order!",
            customer_email="customer@example.com",
            session_id="flow-test",
            route=route,
        )

        # Simulate processing through each actor
        expected_actors = [
            "sentiment_analyzer",
            "intent_analyzer",
            "context_retriever",
            "decision_router",
            "response_generator",
            "guardrail_validator",
            "response_aggregator",
        ]

        for i, expected_actor in enumerate(expected_actors):
            current = message.route.get_current_actor()
            assert current == expected_actor, f"Step {i}: expected {expected_actor}, got {current}"

            # Simulate processing (add some enrichment)
            if current == "sentiment_analyzer":
                message.add_enrichment("sentiment", {"label": "negative", "score": -0.8})
            elif current == "intent_analyzer":
                message.add_enrichment("intent", {"category": "complaint", "confidence": 0.9})
            elif current == "response_generator":
                message.add_enrichment("response", "I apologize for the delay...")

            # Advance to next step (except for last step)
            if i < len(expected_actors) - 1:
                assert message.route.advance() is True
            else:
                # Last step
                assert message.route.is_complete() is True
                assert message.route.advance() is False

        # Verify enrichments were added
        assert message.payload.sentiment is not None
        assert message.payload.intent is not None
        assert message.payload.response is not None

    def test_error_recovery_flow(self):
        """Test error recovery flow."""
        # Create message
        route = Route(
            steps=["actor1", "actor2", "actor3"],
            error_handler="recovery_actor",
            current_step=1,  # Start at actor2
        )
        message = create_support_message(
            customer_message="Test message", customer_email="test@example.com", session_id="error-test", route=route
        )

        # Simulate error at actor2
        message.add_error("processing_error", "Simulated failure", "actor2")
        message.increment_retry()

        # Create error message for recovery
        error_message = create_error_message(
            original_message=message, error_type="processing_error", error_message="Simulated failure", actor="actor2"
        )

        # Verify error routing
        assert error_message.route.steps == ["recovery_actor"]
        assert error_message.route.current_step == 0
        assert error_message.route.get_current_actor() == "recovery_actor"

        # Verify error information preserved
        assert error_message.payload.error is not None
        assert len(error_message.payload.recovery_log) >= 1
        assert error_message.metadata["retry_count"] >= 1

    def test_complex_enrichment_scenario(self):
        """Test complex message enrichment scenario."""
        payload = MessagePayload(
            customer_message="URGENT! My laptop order ORD-12345 is missing and I need it for work tomorrow!",
            customer_email="business@example.com",
        )
        route = StandardRoutes.full_support_flow()
        message = Message(session_id="complex-test", route=route, payload=payload)

        # Simulate enrichments from different actors
        enrichments = {
            "sentiment": {
                "sentiment": {"label": "negative", "score": -0.9, "confidence": 0.95},
                "urgency": {"level": "high", "score": 0.9},
                "is_complaint": True,
            },
            "intent": {
                "intent": {"category": "order_inquiry", "subcategory": "missing_order"},
                "confidence": 0.88,
                "entities": [
                    {"type": "order_id", "value": "ORD-12345"},
                    {"type": "urgency", "value": "urgent"},
                    {"type": "product", "value": "laptop"},
                ],
            },
            "context": {
                "customer_context": {"profile": {"tier": "business", "email": "business@example.com"}},
                "order_context": {"order_id": "ORD-12345", "status": "shipped"},
            },
            "response": "I understand this is urgent and I sincerely apologize...",
            "guardrail_check": {"validation_status": "approved", "approved": True, "issues": []},
        }

        # Apply enrichments
        for field, data in enrichments.items():
            message.add_enrichment(field, data)

        # Verify all enrichments
        assert message.payload.sentiment["sentiment"]["label"] == "negative"
        assert message.payload.intent["confidence"] == 0.88
        assert len(message.payload.intent["entities"]) == 3
        assert message.payload.context["customer_context"]["profile"]["tier"] == "business"
        assert "apologize" in message.payload.response
        assert message.payload.guardrail_check["approved"] is True

        # Verify original data preserved
        assert "URGENT" in message.payload.customer_message
        assert message.payload.customer_email == "business@example.com"
