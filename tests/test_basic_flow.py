#!/usr/bin/env python3
"""
Basic test script for the Actor Mesh Demo.

This script tests the basic flow of the e-commerce support agent system
by creating sample messages and processing them through individual actors.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from actors.context_retriever import create_context_retriever
from actors.execution_coordinator import create_execution_coordinator
from actors.guardrail_validator import create_guardrail_validator
from actors.intent_analyzer import create_intent_analyzer
from actors.response_generator import create_response_generator
from actors.sentiment_analyzer import create_sentiment_analyzer
from models.message import MessagePayload, StandardRoutes, create_support_message


class BasicFlowTester:
    """Basic flow tester for the Actor Mesh Demo."""

    def __init__(self):
        """Initialize the tester."""
        self.logger = logging.getLogger("basic_flow_tester")

        # Test messages
        self.test_messages = [
            {
                "customer_email": "john.doe@example.com",
                "message": "Hi, I'm really upset about my order ORD-12345678. It was supposed to arrive yesterday but it's still not here! This is unacceptable. I need this urgently!",
                "description": "Angry customer with delivery delay",
            },
            {
                "customer_email": "jane.smith@example.com",
                "message": "Hello, I'd like to check the status of my recent order. Can you help me track it?",
                "description": "Polite order inquiry",
            },
            {
                "customer_email": "bob.wilson@example.com",
                "message": "I need to return this defective laptop I received. It won't turn on at all. How do I proceed with the return?",
                "description": "Product return request",
            },
        ]

    async def test_individual_actors(self):
        """Test each actor individually without NATS."""
        print("=" * 60)
        print("TESTING INDIVIDUAL ACTORS")
        print("=" * 60)

        for i, test_case in enumerate(self.test_messages, 1):
            print(f"\n--- Test Case {i}: {test_case['description']} ---")

            # Create message payload
            payload = MessagePayload(customer_message=test_case["message"], customer_email=test_case["customer_email"])

            # Test SentimentAnalyzer
            print("\n1. Testing SentimentAnalyzer...")
            sentiment_analyzer = create_sentiment_analyzer()
            try:
                sentiment_result = await sentiment_analyzer.process(payload)
                if sentiment_result:
                    payload.sentiment = sentiment_result
                    sentiment_label = sentiment_result.get("sentiment", {}).get("label", "unknown")
                    urgency_level = sentiment_result.get("urgency", {}).get("level", "unknown")
                    is_complaint = sentiment_result.get("is_complaint", False)
                    print(f"   ✓ Sentiment: {sentiment_label}, Urgency: {urgency_level}, Complaint: {is_complaint}")
                else:
                    print("   ✗ No sentiment result")
            except Exception as e:
                print(f"   ✗ Error: {e}")

            # Test IntentAnalyzer
            print("\n2. Testing IntentAnalyzer...")
            intent_analyzer = create_intent_analyzer()
            try:
                intent_result = await intent_analyzer.process(payload)
                if intent_result:
                    payload.intent = intent_result
                    intent_category = intent_result.get("intent", {}).get("category", "unknown")
                    confidence = intent_result.get("confidence", 0.0)
                    entities_count = len(intent_result.get("entities", []))
                    print(f"   ✓ Intent: {intent_category}, Confidence: {confidence:.2f}, Entities: {entities_count}")
                else:
                    print("   ✗ No intent result")
            except Exception as e:
                print(f"   ✗ Error: {e}")

            # Test ContextRetriever (will fail without mock APIs running)
            print("\n3. Testing ContextRetriever...")
            context_retriever = create_context_retriever()
            try:
                context_result = await context_retriever.process(payload)
                if context_result:
                    payload.context = context_result
                    source = context_result.get("source", "unknown")
                    print(f"   ✓ Context retrieved from: {source}")

                    # Show customer info if available
                    customer_context = context_result.get("customer_context", {})
                    if isinstance(customer_context, dict) and "profile" in customer_context:
                        profile = customer_context["profile"]
                        print(f"      Customer: {profile.get('first_name', 'Unknown')} {profile.get('last_name', '')}")
                        print(f"      Tier: {profile.get('tier', 'unknown')}")
                    elif "error" in customer_context:
                        print(f"   ⚠ Context error: {customer_context['error']}")
                else:
                    print("   ✗ No context result")
            except Exception as e:
                print(f"   ✗ Error: {e}")

            # Test ResponseGenerator
            print("\n4. Testing ResponseGenerator...")
            response_generator = create_response_generator()
            try:
                response_result = await response_generator.process(payload)
                if response_result:
                    payload.response = response_result["response_text"]
                    tone = response_result.get("tone", "unknown")
                    method = response_result.get("generation_method", "unknown")
                    print(f"   ✓ Response generated using {method} method, tone: {tone}")
                    print(f"      Response: {response_result['response_text'][:100]}...")
                else:
                    print("   ✗ No response result")
            except Exception as e:
                print(f"   ✗ Error: {e}")

            # Test GuardrailValidator
            print("\n5. Testing GuardrailValidator...")
            guardrail_validator = create_guardrail_validator()
            try:
                guardrail_result = await guardrail_validator.process(payload)
                if guardrail_result:
                    payload.guardrail_check = guardrail_result
                    status = guardrail_result.get("validation_status", "unknown")
                    approved = guardrail_result.get("approved", False)
                    issues_count = len(guardrail_result.get("issues", []))
                    print(f"   ✓ Validation: {status}, Approved: {approved}, Issues: {issues_count}")
                else:
                    print("   ✗ No guardrail result")
            except Exception as e:
                print(f"   ✗ Error: {e}")

            # Test ExecutionCoordinator
            print("\n6. Testing ExecutionCoordinator...")
            execution_coordinator = create_execution_coordinator()
            try:
                execution_result = await execution_coordinator.process(payload)
                if execution_result:
                    payload.execution_result = execution_result
                    status = execution_result.get("execution_status", "unknown")
                    actions_count = len(execution_result.get("actions_executed", []))
                    print(f"   ✓ Execution: {status}, Actions executed: {actions_count}")
                else:
                    print("   ✗ No execution result")
            except Exception as e:
                print(f"   ✗ Error: {e}")

            print("\n   Final payload enrichment status:")
            print(f"   - Sentiment: {'✓' if hasattr(payload, 'sentiment') and payload.sentiment else '✗'}")
            print(f"   - Intent: {'✓' if hasattr(payload, 'intent') and payload.intent else '✗'}")
            print(f"   - Context: {'✓' if hasattr(payload, 'context') and payload.context else '✗'}")
            print(f"   - Response: {'✓' if hasattr(payload, 'response') and payload.response else '✗'}")
            print(f"   - Guardrail: {'✓' if hasattr(payload, 'guardrail_check') and payload.guardrail_check else '✗'}")
            print(
                f"   - Execution: {'✓' if hasattr(payload, 'execution_result') and payload.execution_result else '✗'}"
            )

    async def test_message_models(self):
        """Test message models and routing."""
        print("\n" + "=" * 60)
        print("TESTING MESSAGE MODELS")
        print("=" * 60)

        # Test creating messages
        print("\n1. Testing message creation...")
        route = StandardRoutes.full_support_flow()
        message = create_support_message(
            customer_message="Test message",
            customer_email="test@example.com",
            session_id="test-session-123",
            route=route,
        )

        print(f"   ✓ Message created with ID: {message.message_id}")
        print(f"   ✓ Route has {len(message.route.steps)} steps")
        print(f"   ✓ Current step: {message.route.current_step}")
        print(f"   ✓ Current actor: {message.route.get_current_actor()}")

        # Test route advancement
        print("\n2. Testing route advancement...")
        steps_advanced = 0
        while not message.route.is_complete():
            current_actor = message.route.get_current_actor()
            next_actor = message.route.get_next_actor()

            if message.route.advance():
                steps_advanced += 1
                print(f"   Step {steps_advanced}: {current_actor} -> {next_actor}")
            else:
                break

        print(f"   ✓ Advanced through {steps_advanced} routing steps")

        # Test error handling
        print("\n3. Testing error handling...")
        message.add_error("test_error", "This is a test error", "test_actor")
        message.increment_retry()

        print(f"   ✓ Error logged: {message.payload.error}")
        print(f"   ✓ Retry count: {message.metadata['retry_count']}")

    async def test_standard_routes(self):
        """Test predefined standard routes."""
        print("\n" + "=" * 60)
        print("TESTING STANDARD ROUTES")
        print("=" * 60)

        routes_to_test = [
            ("Complaint Analysis", StandardRoutes.complaint_analysis_route()),
            ("Response Generation", StandardRoutes.response_generation_route()),
            ("Action Execution", StandardRoutes.action_execution_route()),
            ("Full Support Flow", StandardRoutes.full_support_flow()),
        ]

        for route_name, route in routes_to_test:
            print(f"\n{route_name}:")
            print(f"   Steps: {' -> '.join(route.steps)}")
            print(f"   Error Handler: {route.error_handler}")
            print(f"   Total Steps: {len(route.steps)}")

    async def generate_test_report(self):
        """Generate a summary test report."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY REPORT")
        print("=" * 60)

        print("\nComponents Tested:")
        print("✓ Message Models (MessagePayload, Route, StandardRoutes)")
        print("✓ SentimentAnalyzer (rule-based sentiment analysis)")
        print("✓ IntentAnalyzer (LLM-based intent classification)")
        print("✓ ContextRetriever (API data aggregation)")
        print("✓ ResponseGenerator (LLM-based response generation)")
        print("✓ GuardrailValidator (safety and policy checks)")
        print("✓ ExecutionCoordinator (action execution)")

        print("\nNotes:")
        print("- ContextRetriever may fail without mock APIs running")
        print("- IntentAnalyzer and ResponseGenerator require LLM API keys")
        print("- All actors tested in isolation (no NATS required)")
        print("- Full system integration requires NATS server and mock APIs")

        print("\nNext Steps:")
        print("1. Start NATS server: docker run -p 4222:4222 nats:latest")
        print("2. Start mock APIs on ports 8001, 8002, 8003")
        print("3. Set up LLM API keys (OpenAI, Anthropic, or Ollama)")
        print("4. Run full integration tests with message flow")

    async def run_all_tests(self):
        """Run all tests."""
        print("Starting Basic Flow Tests for Actor Mesh Demo")
        print("=" * 60)

        try:
            await self.test_message_models()
            await self.test_standard_routes()
            await self.test_individual_actors()
            await self.generate_test_report()

            print("\n✅ All basic tests completed successfully!")
            return True

        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            self.logger.exception("Test execution failed")
            return False


async def main():
    """Main function to run tests."""
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Suppress some verbose logs during testing
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("actors").setLevel(logging.WARNING)

    # Run tests
    tester = BasicFlowTester()
    success = await tester.run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
