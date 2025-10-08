"""
Pytest configuration and shared fixtures for Actor Mesh tests.

This module provides common fixtures, test data, and configuration
used across all test modules in the Actor Mesh E-commerce system.
"""

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from actors.base import BaseActor

# Import project modules
from models.message import Message, MessagePayload, Route, StandardRoutes, create_support_message


# Test Configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# Mock NATS fixtures
@pytest.fixture
def mock_nats_connection():
    """Mock NATS connection."""
    mock_nc = AsyncMock()
    mock_nc.connect = AsyncMock()
    mock_nc.close = AsyncMock()
    return mock_nc


@pytest.fixture
def mock_jetstream():
    """Mock JetStream context."""
    mock_js = AsyncMock()
    mock_js.add_stream = AsyncMock()
    mock_js.stream_info = AsyncMock()
    mock_js.subscribe = AsyncMock()
    mock_js.publish = AsyncMock()
    return mock_js


@pytest.fixture
def mock_nats_message():
    """Mock NATS message."""
    mock_msg = MagicMock()
    mock_msg.ack = AsyncMock()
    mock_msg.nak = AsyncMock()
    return mock_msg


# Test Data Fixtures
@pytest.fixture
def sample_customer_messages():
    """Sample customer messages for testing."""
    return [
        {
            "customer_email": "angry.customer@example.com",
            "message": "This is absolutely terrible! My order ORD-12345 was supposed to arrive yesterday but it's still not here! I'm furious and need this fixed immediately!",
            "expected_sentiment": "negative",
            "expected_urgency": "high",
            "expected_complaint": True,
        },
        {
            "customer_email": "happy.customer@example.com",
            "message": "Thank you so much for the excellent service! My order arrived perfectly and I'm very satisfied with the quality.",
            "expected_sentiment": "positive",
            "expected_urgency": "low",
            "expected_complaint": False,
        },
        {
            "customer_email": "neutral.customer@example.com",
            "message": "I would like to check the status of my order please. Can you provide an update?",
            "expected_sentiment": "neutral",
            "expected_urgency": "low",
            "expected_complaint": False,
        },
        {
            "customer_email": "urgent.customer@example.com",
            "message": "I need to track my order urgently as it contains important documents for a meeting today.",
            "expected_sentiment": "neutral",
            "expected_urgency": "high",
            "expected_complaint": False,
        },
    ]


@pytest.fixture
def sample_message_payload():
    """Create a sample MessagePayload for testing."""
    return MessagePayload(customer_message="Hello, I need help with my order", customer_email="test@example.com")


@pytest.fixture
def sample_enriched_payload():
    """Create a sample enriched MessagePayload for testing."""
    payload = MessagePayload(
        customer_message="I'm really upset about my delayed order!", customer_email="customer@example.com"
    )

    # Add enrichments
    payload.sentiment = {
        "sentiment": {"label": "negative", "score": -0.8, "confidence": 0.9},
        "urgency": {"level": "high", "score": 0.7},
        "is_complaint": True,
    }

    payload.intent = {
        "intent": {"category": "order_inquiry", "subcategory": "delivery_status"},
        "confidence": 0.85,
        "entities": [{"type": "order_id", "value": "ORD-12345"}],
    }

    payload.context = {
        "customer_context": {
            "profile": {"first_name": "John", "last_name": "Doe", "tier": "premium", "email": "customer@example.com"}
        },
        "order_context": {"order_id": "ORD-12345", "status": "shipped", "expected_delivery": "2024-01-15"},
    }

    return payload


@pytest.fixture
def sample_route():
    """Create a sample Route for testing."""
    return Route(
        steps=["sentiment_analyzer", "intent_analyzer", "response_generator"],
        current_step=0,
        error_handler="escalation_router",
    )


@pytest.fixture
def sample_message(sample_message_payload, sample_route):
    """Create a sample Message for testing."""
    return Message(session_id="test-session-123", route=sample_route, payload=sample_message_payload)


@pytest.fixture
def standard_routes():
    """Provide all standard routes for testing."""
    return {
        "complaint_analysis": StandardRoutes.complaint_analysis_route(),
        "response_generation": StandardRoutes.response_generation_route(),
        "action_execution": StandardRoutes.action_execution_route(),
        "full_support_flow": StandardRoutes.full_support_flow(),
    }


# Mock API Response Fixtures
@pytest.fixture
def mock_customer_api_response():
    """Mock customer API response."""
    return {
        "customer_id": "CUST-12345",
        "profile": {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "phone": "+1-555-0123",
            "tier": "premium",
            "registration_date": "2023-01-15",
            "preferences": {"communication_method": "email", "language": "en"},
        },
        "support_history": [
            {
                "ticket_id": "TICK-001",
                "date": "2024-01-10",
                "issue": "Delivery delay",
                "resolution": "Expedited shipping",
            }
        ],
    }


@pytest.fixture
def mock_orders_api_response():
    """Mock orders API response."""
    return {
        "orders": [
            {
                "order_id": "ORD-12345",
                "status": "shipped",
                "items": [{"product_id": "PROD-001", "name": "Laptop", "quantity": 1, "price": 999.99}],
                "shipping_address": {"street": "123 Main St", "city": "Anytown", "state": "CA", "zip": "12345"},
                "order_date": "2024-01-10",
                "expected_delivery": "2024-01-15",
                "total": 999.99,
            }
        ]
    }


@pytest.fixture
def mock_tracking_api_response():
    """Mock tracking API response."""
    return {
        "tracking_number": "TRACK-12345",
        "status": "in_transit",
        "location": "Distribution Center - Los Angeles, CA",
        "estimated_delivery": "2024-01-15",
        "tracking_history": [
            {"date": "2024-01-10", "status": "shipped", "location": "Fulfillment Center - San Francisco, CA"},
            {"date": "2024-01-12", "status": "in_transit", "location": "Distribution Center - Los Angeles, CA"},
        ],
    }


# LLM Response Fixtures
@pytest.fixture
def mock_llm_intent_response():
    """Mock LLM response for intent analysis."""
    return {
        "intent": {"category": "order_inquiry", "subcategory": "delivery_status"},
        "confidence": 0.85,
        "entities": [{"type": "order_id", "value": "ORD-12345"}, {"type": "emotion", "value": "frustrated"}],
        "reasoning": "Customer is asking about order delivery status with emotional language",
    }


@pytest.fixture
def mock_llm_response_generation():
    """Mock LLM response for response generation."""
    return {
        "response_text": "I sincerely apologize for the delay with your order ORD-12345. I understand your frustration, and I'm here to help resolve this immediately. Let me check the tracking details and provide you with an update.",
        "tone": "empathetic_professional",
        "key_points": ["Acknowledged frustration", "Apologized for delay", "Offered immediate assistance"],
        "confidence": 0.92,
    }


# Storage Mock Fixtures
@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.ping = AsyncMock(return_value=True)
    return mock_redis


@pytest.fixture
def mock_sqlite_client():
    """Mock SQLite client."""
    mock_sqlite = AsyncMock()
    mock_sqlite.execute = AsyncMock()
    mock_sqlite.fetch_one = AsyncMock(return_value=None)
    mock_sqlite.fetch_all = AsyncMock(return_value=[])
    mock_sqlite.close = AsyncMock()
    return mock_sqlite


# Test Actor Base Class
class TestActor(BaseActor):
    """Test actor implementation for unit testing."""

    def __init__(self, name: str = "test_actor", nats_url: str = "nats://localhost:4222"):
        super().__init__(name, nats_url)
        self.process_result = {"test": "result"}
        self.process_called = False
        self.process_call_count = 0

    async def process(self, payload: MessagePayload) -> Dict[str, Any]:
        """Mock process method."""
        self.process_called = True
        self.process_call_count += 1
        return self.process_result


@pytest.fixture
def test_actor():
    """Create a test actor for testing base functionality."""
    return TestActor()


# HTTP Mock Fixtures
@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for API calls."""
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.put = AsyncMock(return_value=mock_response)
    mock_client.delete = AsyncMock(return_value=mock_response)
    return mock_client


# Environment Mock Fixtures
@pytest.fixture
def mock_env_vars():
    """Mock environment variables."""
    env_vars = {
        "OPENAI_API_KEY": "test-openai-key",
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "REDIS_URL": "redis://localhost:6379",
        "NATS_URL": "nats://localhost:4222",
        "DATABASE_URL": "sqlite:///test.db",
    }

    with patch.dict("os.environ", env_vars):
        yield env_vars


# Utility Functions for Tests
def create_test_message(
    customer_message: str = "Test message",
    customer_email: str = "test@example.com",
    session_id: str = None,
    route: Route = None,
) -> Message:
    """Utility function to create test messages."""
    if session_id is None:
        session_id = f"test-session-{uuid.uuid4()}"

    if route is None:
        route = Route(steps=["test_actor"], current_step=0)

    return create_support_message(
        customer_message=customer_message, customer_email=customer_email, session_id=session_id, route=route
    )


def assert_message_enriched(message: Message, field: str, expected_keys: List[str] = None):
    """Utility function to assert message enrichment."""
    payload_data = getattr(message.payload, field, None)
    assert payload_data is not None, f"Message payload missing {field}"

    if expected_keys:
        for key in expected_keys:
            assert key in payload_data, f"Missing key '{key}' in {field}"


def assert_actor_processed(actor, expected_call_count: int = 1):
    """Utility function to assert actor processing."""
    assert hasattr(actor, "process_called"), "Actor should have process_called attribute"
    assert actor.process_called, "Actor process method should have been called"
    assert actor.process_call_count == expected_call_count, (
        f"Expected {expected_call_count} process calls, got {actor.process_call_count}"
    )


# Async Test Utilities
async def wait_for_condition(condition_func, timeout: float = 5.0, interval: float = 0.1):
    """Wait for a condition to become true."""
    import time

    start_time = time.time()

    while time.time() - start_time < timeout:
        if condition_func():
            return True
        await asyncio.sleep(interval)

    return False


# Test Data Generators
def generate_test_messages(count: int = 5) -> List[Dict[str, Any]]:
    """Generate test messages for bulk testing."""
    messages = []
    sentiments = ["positive", "negative", "neutral"]
    urgencies = ["low", "medium", "high"]

    for i in range(count):
        messages.append(
            {
                "customer_email": f"customer{i}@example.com",
                "message": f"Test message {i} for testing purposes",
                "session_id": f"test-session-{i}",
                "expected_sentiment": sentiments[i % len(sentiments)],
                "expected_urgency": urgencies[i % len(urgencies)],
            }
        )

    return messages


# Performance Testing Fixtures
@pytest.fixture
def performance_config():
    """Configuration for performance testing."""
    return {
        "max_processing_time": 5.0,  # seconds
        "max_memory_usage": 100 * 1024 * 1024,  # 100MB
        "concurrent_messages": 10,
        "stress_test_duration": 30,  # seconds
    }


# Integration Test Fixtures
@pytest.fixture
def integration_test_config():
    """Configuration for integration testing."""
    return {
        "nats_url": "nats://localhost:4222",
        "redis_url": "redis://localhost:6379",
        "mock_api_ports": {
            "customer_api": 8001,
            "orders_api": 8002,
            "tracking_api": 8003,
        },
        "test_timeout": 30.0,
    }


# Cleanup Fixtures
@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Automatic cleanup after each test."""
    yield
    # Cleanup code can be added here if needed
    # For example, clearing Redis test data, closing connections, etc.
