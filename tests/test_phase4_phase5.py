#!/usr/bin/env python3
"""
Comprehensive Test for Phase 4 and Phase 5 Implementation.

This script tests the newly implemented DecisionRouter, EscalationRouter,
ResponseAggregator, and API Gateway components to ensure they work correctly
within the Actor Mesh architecture.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import httpx
import nats

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from actors.decision_router import DecisionRouter
from actors.escalation_router import EscalationRouter
from actors.response_aggregator import ResponseAggregator
from api.gateway import APIGateway
from models.message import Message, MessagePayload, Route, StandardRoutes


class Phase4Phase5Tester:
    """Comprehensive tester for Phase 4 and Phase 5 implementations."""

    def __init__(self):
        """Initialize the tester."""
        self.setup_logging()
        self.nats_url = "nats://localhost:4222"
        self.api_gateway_url = "http://localhost:8000"

        # Test results
        self.test_results = {
            "decision_router": {"passed": 0, "failed": 0, "errors": []},
            "escalation_router": {"passed": 0, "failed": 0, "errors": []},
            "response_aggregator": {"passed": 0, "failed": 0, "errors": []},
            "api_gateway": {"passed": 0, "failed": 0, "errors": []},
            "integration": {"passed": 0, "failed": 0, "errors": []},
        }

    def setup_logging(self):
        """Setup logging for the test."""
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger("phase4_phase5_tester")

    async def run_all_tests(self):
        """Run all tests for Phase 4 and Phase 5."""
        self.logger.info("🚀 Starting Phase 4 and Phase 5 comprehensive tests")

        try:
            # Test Phase 4: Router Actors
            await self.test_decision_router()
            await self.test_escalation_router()

            # Test Phase 5: Entry/Exit Points
            await self.test_response_aggregator()
            await self.test_api_gateway()

            # Test Integration
            await self.test_end_to_end_integration()

            # Print results
            self.print_test_summary()

        except Exception as e:
            self.logger.error(f"Critical error in test suite: {str(e)}")
            raise

    async def test_decision_router(self):
        """Test DecisionRouter functionality."""
        self.logger.info("🧭 Testing DecisionRouter...")

        try:
            router = DecisionRouter()
            await router.start()

            # Test 1: Critical escalation
            await self._test_critical_escalation(router)

            # Test 2: Priority processing
            await self._test_priority_processing(router)

            # Test 3: Action execution routing
            await self._test_action_execution_routing(router)

            # Test 4: Low confidence handling
            await self._test_low_confidence_handling(router)

            # Test 5: Complex query routing
            await self._test_complex_query_routing(router)

            await router.stop()
            self.logger.info("✅ DecisionRouter tests completed")

        except Exception as e:
            self._record_error("decision_router", f"DecisionRouter test failed: {str(e)}")

    async def _test_critical_escalation(self, router: DecisionRouter):
        """Test critical escalation logic."""
        message = self._create_test_message(
            customer_message="I am FURIOUS! This is completely unacceptable!",
            enrichments={
                "sentiment": {"sentiment": "negative", "urgency": "critical", "intensity": 0.9},
                "intent": {"intent": "complaint", "confidence": 0.8},
            },
        )

        original_steps = message.route.steps.copy()
        await router.route_message(message)

        # Should route to escalation_router
        if "escalation_router" in message.route.steps and "response_aggregator" in message.route.steps:
            self._record_pass("decision_router", "Critical escalation routing")
        else:
            self._record_fail("decision_router", f"Critical escalation failed. Route: {message.route.steps}")

    async def _test_priority_processing(self, router: DecisionRouter):
        """Test priority processing for high urgency messages."""
        message = self._create_test_message(
            customer_message="I need urgent help with my billing issue",
            enrichments={
                "sentiment": {"sentiment": "neutral", "urgency": "high"},
                "intent": {"intent": "billing_inquiry", "confidence": 0.9},
            },
        )

        await router.route_message(message)

        # Should have response_generator in early position
        generator_index = None
        try:
            generator_index = message.route.steps.index("response_generator")
        except ValueError:
            pass

        if generator_index is not None and generator_index < 5:
            self._record_pass("decision_router", "Priority processing routing")
        else:
            self._record_fail("decision_router", f"Priority processing failed. Route: {message.route.steps}")

    async def _test_action_execution_routing(self, router: DecisionRouter):
        """Test routing for messages that need action execution."""
        message = self._create_test_message(
            customer_message="I need a refund for my order",
            enrichments={
                "sentiment": {"sentiment": "neutral", "urgency": "medium"},
                "intent": {"intent": "refund_request", "confidence": 0.8},
            },
        )

        await router.route_message(message)

        if "execution_coordinator" in message.route.steps:
            self._record_pass("decision_router", "Action execution routing")
        else:
            self._record_fail("decision_router", f"Action execution routing failed. Route: {message.route.steps}")

    async def _test_low_confidence_handling(self, router: DecisionRouter):
        """Test handling of low confidence intent analysis."""
        message = self._create_test_message(
            customer_message="Um, I have some kind of issue maybe?",
            enrichments={
                "sentiment": {"sentiment": "neutral", "urgency": "low"},
                "intent": {"intent": "general_inquiry", "confidence": 0.3},
            },
        )

        await router.route_message(message)

        if "escalation_router" in message.route.steps:
            self._record_pass("decision_router", "Low confidence handling")
        else:
            self._record_fail("decision_router", f"Low confidence handling failed. Route: {message.route.steps}")

    async def _test_complex_query_routing(self, router: DecisionRouter):
        """Test routing for complex queries."""
        message = self._create_test_message(
            customer_message="I need technical support for compatibility issues",
            enrichments={
                "sentiment": {"sentiment": "neutral", "urgency": "medium"},
                "intent": {"intent": "technical_support", "confidence": 0.7},
                "context": {"orders": [{"id": f"ORD-{i}"} for i in range(10)]},  # Many orders
            },
        )

        await router.route_message(message)

        # Should ensure context_retriever is called
        if "context_retriever" in message.route.steps[message.route.current_step :]:
            self._record_pass("decision_router", "Complex query routing")
        else:
            self._record_fail("decision_router", f"Complex query routing failed. Route: {message.route.steps}")

    async def test_escalation_router(self):
        """Test EscalationRouter functionality."""
        self.logger.info("🚨 Testing EscalationRouter...")

        try:
            router = EscalationRouter()
            await router.start()

            # Test 1: Retry logic
            await self._test_retry_logic(router)

            # Test 2: Human handoff
            await self._test_human_handoff(router)

            # Test 3: Error recovery
            await self._test_error_recovery(router)

            # Test 4: Fallback response
            await self._test_fallback_response(router)

            # Test 5: No escalation needed
            await self._test_no_escalation(router)

            await router.stop()
            self.logger.info("✅ EscalationRouter tests completed")

        except Exception as e:
            self._record_error("escalation_router", f"EscalationRouter test failed: {str(e)}")

    async def _test_retry_logic(self, router: EscalationRouter):
        """Test retry logic for failed operations."""
        message = self._create_test_message(customer_message="Test message for retry", enrichments={})

        # Simulate error
        message.add_error("api_timeout", "Timeout occurred", "context_retriever")
        message.metadata["retry_count"] = 1

        await router.route_message(message)

        if message.metadata["retry_count"] == 2:
            self._record_pass("escalation_router", "Retry logic")
        else:
            self._record_fail(
                "escalation_router", f"Retry logic failed. Retry count: {message.metadata.get('retry_count')}"
            )

    async def _test_human_handoff(self, router: EscalationRouter):
        """Test human handoff logic."""
        message = self._create_test_message(
            customer_message="I want to speak to a manager NOW!",
            enrichments={
                "sentiment": {"sentiment": "negative", "urgency": "high", "intensity": 0.8},
                "intent": {"intent": "escalation_request", "confidence": 0.9},
            },
        )

        await router.route_message(message)

        context = message.payload.context or {}
        if "escalation" in context and context["escalation"].get("escalated_at"):
            self._record_pass("escalation_router", "Human handoff")
        else:
            self._record_fail("escalation_router", "Human handoff failed")

    async def _test_error_recovery(self, router: EscalationRouter):
        """Test error recovery after max retries."""
        message = self._create_test_message(customer_message="Test message for error recovery", enrichments={})

        # Simulate max retries exceeded
        message.add_error("llm_error", "LLM service unavailable", "response_generator")
        message.metadata["retry_count"] = 4  # Exceeds max

        original_response = message.payload.response
        await router.route_message(message)

        # Should have generated fallback response
        if message.payload.response and message.payload.response != original_response:
            self._record_pass("escalation_router", "Error recovery")
        else:
            self._record_fail("escalation_router", "Error recovery failed")

    async def _test_fallback_response(self, router: EscalationRouter):
        """Test fallback response generation."""
        message = self._create_test_message(
            customer_message="Test message for fallback",
            enrichments={"guardrail_check": {"passed": False, "issues": ["inappropriate_content"]}},
        )

        await router.route_message(message)

        if message.payload.response and "Reference ID:" in message.payload.response:
            self._record_pass("escalation_router", "Fallback response")
        else:
            self._record_fail("escalation_router", "Fallback response failed")

    async def _test_no_escalation(self, router: EscalationRouter):
        """Test normal flow when no escalation is needed."""
        message = self._create_test_message(
            customer_message="Just a normal question",
            enrichments={
                "sentiment": {"sentiment": "neutral", "urgency": "low"},
                "intent": {"intent": "general_inquiry", "confidence": 0.8},
            },
        )

        original_step = message.route.current_step
        await router.route_message(message)

        # Should advance to next step
        if message.route.current_step > original_step:
            self._record_pass("escalation_router", "No escalation needed")
        else:
            self._record_fail("escalation_router", "No escalation logic failed")

    async def test_response_aggregator(self):
        """Test ResponseAggregator functionality."""
        self.logger.info("📦 Testing ResponseAggregator...")

        try:
            aggregator = ResponseAggregator()
            await aggregator.start()

            # Test 1: Normal response processing
            await self._test_normal_response_processing(aggregator)

            # Test 2: Response with enrichments
            await self._test_response_with_enrichments(aggregator)

            # Test 3: Error response handling
            await self._test_error_response_handling(aggregator)

            # Test 4: Fallback response generation
            await self._test_aggregator_fallback_response(aggregator)

            await aggregator.stop()
            self.logger.info("✅ ResponseAggregator tests completed")

        except Exception as e:
            self._record_error("response_aggregator", f"ResponseAggregator test failed: {str(e)}")

    async def _test_normal_response_processing(self, aggregator: ResponseAggregator):
        """Test normal response processing."""
        message = self._create_test_message(
            customer_message="Thank you for your help",
            enrichments={
                "sentiment": {"sentiment": "positive", "urgency": "low"},
                "intent": {"intent": "thank_you", "confidence": 0.9},
            },
        )
        message.payload.response = "You're welcome! Is there anything else I can help you with?"
        message.metadata["gateway_timestamp"] = datetime.now(timezone.utc).isoformat()

        # Mock NATS publish to capture response
        published_data = None
        original_publish = aggregator.nc.publish

        async def mock_publish(subject, data):
            nonlocal published_data
            published_data = json.loads(data.decode())

        aggregator.nc.publish = mock_publish

        await aggregator.process(message)

        if published_data and published_data.get("response") == message.payload.response:
            self._record_pass("response_aggregator", "Normal response processing")
        else:
            self._record_fail("response_aggregator", "Normal response processing failed")

        # Restore original method
        aggregator.nc.publish = original_publish

    async def _test_response_with_enrichments(self, aggregator: ResponseAggregator):
        """Test response processing with full enrichments."""
        message = self._create_test_message(
            customer_message="What's my order status?",
            enrichments={
                "sentiment": {"sentiment": "neutral", "urgency": "medium"},
                "intent": {"intent": "order_status", "confidence": 0.9},
                "context": {"customer": {"tier": "Premium"}, "orders": [{"id": "ORD-123"}]},
                "execution_result": {"success": True, "actions": [{"type": "order_lookup"}]},
                "guardrail_check": {"passed": True, "checks": ["safety", "policy"]},
            },
        )
        message.payload.response = "Your order ORD-123 is being processed."

        published_data = None

        async def mock_publish(subject, data):
            nonlocal published_data
            published_data = json.loads(data.decode())

        aggregator.nc.publish = mock_publish

        await aggregator.process(message)

        metadata = published_data.get("metadata", {}) if published_data else {}
        enrichments = metadata.get("enrichments", {})

        expected_enrichments = [
            "sentiment_analysis",
            "intent_classification",
            "context_retrieval",
            "action_execution",
            "guardrail_validation",
        ]

        if all(enrichments.get(e) for e in expected_enrichments):
            self._record_pass("response_aggregator", "Response with enrichments")
        else:
            self._record_fail("response_aggregator", f"Enrichments missing: {enrichments}")

    async def _test_error_response_handling(self, aggregator: ResponseAggregator):
        """Test error response handling."""
        message = self._create_test_message(customer_message="Test error handling", enrichments={})
        message.add_error("processing_error", "Something went wrong", "test_actor")
        message.payload.response = "I apologize for the technical issue."

        published_data = None

        async def mock_publish(subject, data):
            nonlocal published_data
            published_data = json.loads(data.decode())

        aggregator.nc.publish = mock_publish

        await aggregator.process(message)

        metadata = published_data.get("metadata", {}) if published_data else {}

        if metadata.get("error_occurred") and metadata.get("error_type") == "processing_error":
            self._record_pass("response_aggregator", "Error response handling")
        else:
            self._record_fail("response_aggregator", "Error response handling failed")

    async def _test_aggregator_fallback_response(self, aggregator: ResponseAggregator):
        """Test fallback response generation when no response exists."""
        message = self._create_test_message(
            customer_message="Help with order", enrichments={"intent": {"intent": "order_status", "confidence": 0.7}}
        )
        # No response set - should generate fallback

        published_data = None

        async def mock_publish(subject, data):
            nonlocal published_data
            published_data = json.loads(data.decode())

        aggregator.nc.publish = mock_publish

        await aggregator.process(message)

        response_text = published_data.get("response", "") if published_data else ""

        if response_text and "order" in response_text.lower():
            self._record_pass("response_aggregator", "Fallback response generation")
        else:
            self._record_fail("response_aggregator", "Fallback response generation failed")

    async def test_api_gateway(self):
        """Test API Gateway functionality."""
        self.logger.info("🌐 Testing API Gateway...")

        try:
            # Test 1: Health endpoint
            await self._test_gateway_health()

            # Test 2: Root endpoint
            await self._test_gateway_root()

            # Test 3: Chat endpoint (mock)
            await self._test_gateway_chat_mock()

            self.logger.info("✅ API Gateway tests completed")

        except Exception as e:
            self._record_error("api_gateway", f"API Gateway test failed: {str(e)}")

    async def _test_gateway_health(self):
        """Test API Gateway health endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_gateway_url}/api/health", timeout=5.0)

                if response.status_code == 200:
                    data = response.json()
                    if "status" in data and "timestamp" in data:
                        self._record_pass("api_gateway", "Health endpoint")
                    else:
                        self._record_fail("api_gateway", f"Invalid health response: {data}")
                else:
                    self._record_fail("api_gateway", f"Health endpoint returned {response.status_code}")

        except Exception as e:
            self._record_fail("api_gateway", f"Health endpoint error: {str(e)}")

    async def _test_gateway_root(self):
        """Test API Gateway root endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_gateway_url}/", timeout=5.0)

                if response.status_code == 200:
                    data = response.json()
                    if "service" in data and "endpoints" in data:
                        self._record_pass("api_gateway", "Root endpoint")
                    else:
                        self._record_fail("api_gateway", f"Invalid root response: {data}")
                else:
                    self._record_fail("api_gateway", f"Root endpoint returned {response.status_code}")

        except Exception as e:
            self._record_fail("api_gateway", f"Root endpoint error: {str(e)}")

    async def _test_gateway_chat_mock(self):
        """Test API Gateway chat endpoint with mock data."""
        # This test checks the structure without requiring full actor pipeline
        gateway = APIGateway()

        # Test request validation
        from api.gateway import ChatRequest

        try:
            request = ChatRequest(message="Hello, I need help with my order", customer_email="test@example.com")

            if request.message and request.customer_email:
                self._record_pass("api_gateway", "Chat request validation")
            else:
                self._record_fail("api_gateway", "Chat request validation failed")

        except Exception as e:
            self._record_fail("api_gateway", f"Chat request validation error: {str(e)}")

    async def test_end_to_end_integration(self):
        """Test end-to-end integration of all Phase 4 and Phase 5 components."""
        self.logger.info("🔄 Testing end-to-end integration...")

        try:
            # Test message flow through all new components
            await self._test_message_flow_integration()

            # Test error propagation
            await self._test_error_propagation_integration()

            self.logger.info("✅ End-to-end integration tests completed")

        except Exception as e:
            self._record_error("integration", f"Integration test failed: {str(e)}")

    async def _test_message_flow_integration(self):
        """Test complete message flow through new components."""
        # Create a message that will go through decision routing
        message = self._create_test_message(
            customer_message="I'm very upset about my delayed order ORD-123!",
            enrichments={
                "sentiment": {"sentiment": "negative", "urgency": "high", "intensity": 0.7},
                "intent": {"intent": "delivery_complaint", "confidence": 0.9},
                "context": {"customer": {"tier": "Premium"}, "orders": [{"id": "ORD-123", "status": "delayed"}]},
            },
        )

        # Test decision router
        router = DecisionRouter()
        await router.start()

        original_steps = len(message.route.steps)
        await router.route_message(message)

        # Should have modified the route
        if len(message.route.steps) >= original_steps:
            self._record_pass("integration", "Decision router integration")
        else:
            self._record_fail("integration", "Decision router integration failed")

        # Test response aggregator with the routed message
        message.payload.response = "I understand your frustration. Let me help you with your order."

        aggregator = ResponseAggregator()
        await aggregator.start()

        # Mock publish to capture result
        published_data = None

        async def mock_publish(subject, data):
            nonlocal published_data
            published_data = json.loads(data.decode())

        aggregator.nc.publish = mock_publish

        await aggregator.process(message)

        if published_data and published_data.get("message_id") == message.message_id:
            self._record_pass("integration", "Response aggregator integration")
        else:
            self._record_fail("integration", "Response aggregator integration failed")

        await router.stop()
        await aggregator.stop()

    async def _test_error_propagation_integration(self):
        """Test error propagation through escalation router."""
        message = self._create_test_message(customer_message="Test error propagation", enrichments={})

        # Simulate error
        message.add_error("test_error", "Simulated error for testing", "test_component")

        # Test escalation router
        escalation_router = EscalationRouter()
        await escalation_router.start()

        await escalation_router.route_message(message)

        # Should have handled the error (either retry or fallback)
        if (
            message.metadata.get("retry_count", 0) > 0
            or message.payload.response
            or message.metadata.get("fallback_used")
        ):
            self._record_pass("integration", "Error propagation")
        else:
            self._record_fail("integration", "Error propagation failed")

        await escalation_router.stop()

    def _create_test_message(self, customer_message: str, enrichments: Dict[str, Any]) -> Message:
        """Create a test message with specified enrichments."""
        payload = MessagePayload(customer_message=customer_message, customer_email="test@example.com")

        # Apply enrichments
        for field, data in enrichments.items():
            setattr(payload, field, data)

        route = Route(steps=StandardRoutes.FULL_PROCESSING_PIPELINE.copy())

        return Message(session_id="test_session", route=route, payload=payload, metadata={"test": True})

    def _record_pass(self, category: str, test_name: str):
        """Record a passed test."""
        self.test_results[category]["passed"] += 1
        self.logger.info(f"✅ {test_name}")

    def _record_fail(self, category: str, error_message: str):
        """Record a failed test."""
        self.test_results[category]["failed"] += 1
        self.test_results[category]["errors"].append(error_message)
        self.logger.error(f"❌ {error_message}")

    def _record_error(self, category: str, error_message: str):
        """Record a test error."""
        self.test_results[category]["failed"] += 1
        self.test_results[category]["errors"].append(error_message)
        self.logger.error(f"💥 {error_message}")

    def print_test_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "=" * 60)
        print("PHASE 4 & PHASE 5 TEST SUMMARY")
        print("=" * 60)

        total_passed = sum(results["passed"] for results in self.test_results.values())
        total_failed = sum(results["failed"] for results in self.test_results.values())
        total_tests = total_passed + total_failed

        print("\nOverall Results:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {total_passed} ✅")
        print(f"  Failed: {total_failed} ❌")
        print(f"  Success Rate: {(total_passed / max(total_tests, 1) * 100):.1f}%")

        print("\nDetailed Results:")
        for category, results in self.test_results.items():
            passed = results["passed"]
            failed = results["failed"]
            total = passed + failed

            if total > 0:
                print(f"  {category.replace('_', ' ').title()}:")
                print(f"    Passed: {passed}/{total}")
                print(f"    Failed: {failed}/{total}")

                if results["errors"]:
                    print("    Errors:")
                    for error in results["errors"]:
                        print(f"      - {error}")

        print("\n" + "=" * 60)

        if total_failed == 0:
            print("🎉 ALL TESTS PASSED! Phase 4 and Phase 5 implementation is working correctly.")
        else:
            print(f"⚠️  {total_failed} tests failed. Please review the errors above.")

        print("=" * 60 + "\n")


async def main():
    """Main test function."""
    print("🚀 Phase 4 & Phase 5 Implementation Test")
    print("=========================================")

    # Check if NATS is running
    try:
        nc = await nats.connect("nats://localhost:4222")
        await nc.close()
        print("✅ NATS connection verified")
    except Exception as e:
        print(f"❌ NATS connection failed: {str(e)}")
        print("Please ensure NATS is running with: make start-infrastructure")
        return

    # Run tests
    tester = Phase4Phase5Tester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
