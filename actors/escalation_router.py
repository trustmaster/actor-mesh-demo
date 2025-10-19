"""
Escalation Router Actor for the E-commerce Support Agent.

This router handles escalations, errors, and cases that require human intervention.
It manages the handoff process and provides fallback routing for failed operations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from models.message import Message, MessagePayload

from actors.base import RouterActor


class EscalationRouter(RouterActor):
    """
    Router that handles escalations, errors, and human handoffs.

    The EscalationRouter manages cases that cannot be handled automatically,
    including system errors, low-confidence responses, and customer escalations.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        super().__init__("escalation_router", nats_url)
        self.logger = logging.getLogger("actor.escalation_router")

        # Escalation thresholds and configuration
        self.max_auto_retries = 3
        self.confidence_threshold = 0.5
        self.error_escalation_delay = 30  # seconds

        # Human agent simulation (in a real system, this would be actual agents)
        self.human_agent_available = True
        self.queue_position = 0

    async def route_message(self, message: Message) -> None:
        """
        Handle escalation routing based on message state and errors.

        Args:
            message: The message to evaluate for escalation
        """
        try:
            self.logger.info(f"Processing escalation for message {message.message_id}")

            escalation_type = self._determine_escalation_type(message)

            if escalation_type == "no_escalation":
                # Continue normal processing
                await self._continue_normal_flow(message)
            elif escalation_type == "retry":
                # Retry failed operation
                await self._handle_retry(message)
            elif escalation_type == "human_handoff":
                # Escalate to human agent
                await self._handle_human_handoff(message)
            elif escalation_type == "error_recovery":
                # Attempt error recovery
                await self._handle_error_recovery(message)
            elif escalation_type == "fallback_response":
                # Generate fallback response
                await self._handle_fallback_response(message)
            else:
                self.logger.warning(f"Unknown escalation type: {escalation_type}")
                await self._handle_fallback_response(message)

        except Exception as e:
            self.logger.error(f"Error in escalation routing: {str(e)}")
            await self._handle_critical_error(message, str(e))

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Process method required by BaseActor - not used for router actors.

        Args:
            payload: The message payload to process

        Returns:
            None as router actors handle routing directly
        """
        return None

    def _determine_escalation_type(self, message: Message) -> str:
        """
        Determine the type of escalation needed for the message.

        Returns:
            The escalation type: 'no_escalation', 'retry', 'human_handoff',
            'error_recovery', or 'fallback_response'
        """
        # Check for errors
        if message.payload.error:
            error_info = message.payload.error
            retry_count = message.metadata.get("retry_count", 0)

            # If we haven't exceeded retry limit, try retry
            if retry_count < self.max_auto_retries:
                return "retry"
            else:
                return "error_recovery"

        # Check for low confidence
        intent = message.payload.intent or {}
        if intent.get("confidence", 1.0) < self.confidence_threshold:
            return "human_handoff"

        # Check for explicit escalation requests
        if self._is_escalation_request(message):
            return "human_handoff"

        # Check for critical sentiment that needs human touch
        if self._needs_human_intervention(message):
            return "human_handoff"

        # Check for failed guardrails
        guardrail_check = message.payload.guardrail_check or {}
        if not guardrail_check.get("passed", True):
            return "fallback_response"

        # No escalation needed
        return "no_escalation"

    def _is_escalation_request(self, message: Message) -> bool:
        """Check if the customer explicitly requested escalation."""
        customer_message = message.payload.customer_message.lower()
        escalation_keywords = [
            "manager",
            "supervisor",
            "human",
            "person",
            "speak to someone",
            "escalate",
            "complaint",
            "unsatisfied",
            "not happy",
        ]

        return any(keyword in customer_message for keyword in escalation_keywords)

    def _needs_human_intervention(self, message: Message) -> bool:
        """Check if sentiment/context indicates need for human intervention."""
        sentiment = message.payload.sentiment or {}
        context = message.payload.context or {}

        # Very negative sentiment
        if sentiment.get("sentiment") == "negative" and sentiment.get("intensity", 0) > 0.7:
            return True

        # VIP customer with any issue
        customer_tier = context.get("customer", {}).get("tier", "")
        if customer_tier == "VIP":
            return True

        # Legal or regulatory issues
        intent = message.payload.intent or {}
        if intent.get("intent") in ["legal_threat", "formal_complaint"]:
            return True

        return False

    async def _continue_normal_flow(self, message: Message) -> None:
        """Continue with normal message processing."""
        self.logger.info(f"No escalation needed for message {message.message_id}")
        await self._send_to_next_actor(message)

    async def _handle_retry(self, message: Message) -> None:
        """Handle retry of a failed operation."""
        retry_count = message.metadata.get("retry_count", 0)
        message.metadata["retry_count"] = retry_count + 1

        self.logger.info(f"Retrying message {message.message_id} (attempt {retry_count + 1})")

        # Determine which step failed and retry from there
        failed_step = self._find_failed_step(message)
        if failed_step:
            # Reset to failed step for retry
            message.route.current_step = message.route.steps.index(failed_step)
            # Clear error to allow retry
            message.payload.error = None

            await self._send_to_specific_actor(message, failed_step)
        else:
            # If we can't determine failed step, continue normal flow
            await self._send_to_next_actor(message)

    async def _handle_human_handoff(self, message: Message) -> None:
        """Handle escalation to human agent."""
        self.logger.info(f"Escalating message {message.message_id} to human agent")

        # In a real system, this would queue for human agents
        # For demo purposes, we'll simulate the handoff

        handoff_info = {
            "escalated_at": datetime.now(timezone.utc).isoformat(),
            "escalation_reason": self._get_escalation_reason(message),
            "queue_position": self.queue_position,
            "estimated_wait_time": "5-10 minutes" if self.human_agent_available else "30+ minutes",
        }

        # Add escalation info to payload
        message.payload.context = message.payload.context or {}
        message.payload.context["escalation"] = handoff_info

        # Generate interim response
        interim_response = self._generate_interim_response(message, handoff_info)
        message.payload.response = interim_response

        # In a real system, this would go to human agent queue
        # For demo, we'll send to response aggregator with escalation notice
        await self._send_to_response_aggregator(message)

        self.queue_position += 1

    async def _handle_error_recovery(self, message: Message) -> None:
        """Handle error recovery when retries are exhausted."""
        self.logger.warning(f"Error recovery for message {message.message_id} after max retries")

        error_info = message.payload.error or {}
        error_type = error_info.get("type", "unknown")

        # Try different recovery strategies based on error type
        if error_type in ["llm_error", "api_timeout"]:
            # Use fallback response generation
            await self._handle_fallback_response(message)
        elif error_type == "context_error":
            # Skip context retrieval and continue
            message.payload.context = {"error_recovery": True}
            await self._send_to_next_actor(message)
        else:
            # Generic error recovery - generate safe response
            await self._handle_fallback_response(message)

    async def _handle_fallback_response(self, message: Message) -> None:
        """Generate a safe fallback response."""
        self.logger.info(f"Generating fallback response for message {message.message_id}")

        # Generate appropriate fallback based on situation
        fallback_response = self._generate_fallback_response(message)
        message.payload.response = fallback_response

        # Mark as fallback for monitoring
        message.metadata["fallback_used"] = True
        message.metadata["fallback_reason"] = "escalation_router"

        await self._send_to_response_aggregator(message)

    def _find_failed_step(self, message: Message) -> Optional[str]:
        """Find which step failed based on error information."""
        error_info = message.payload.error or {}
        failed_actor = error_info.get("actor")

        if failed_actor and failed_actor in message.route.steps:
            return failed_actor

        return None

    def _get_escalation_reason(self, message: Message) -> str:
        """Get human-readable escalation reason."""
        if message.payload.error:
            return "System error requiring human assistance"

        intent = message.payload.intent or {}
        if intent.get("confidence", 1.0) < self.confidence_threshold:
            return "Low confidence in automated response"

        if self._is_escalation_request(message):
            return "Customer requested human agent"

        if self._needs_human_intervention(message):
            return "Sensitive issue requiring human attention"

        return "General escalation"

    def _generate_interim_response(self, message: Message, handoff_info: Dict[str, Any]) -> str:
        """Generate interim response for human handoff."""
        customer_email = message.payload.customer_email
        estimated_wait = handoff_info.get("estimated_wait_time", "shortly")

        return f"""Thank you for contacting us. I understand your concern and want to ensure you receive the best possible assistance.

I'm connecting you with one of our human customer service representatives who will be able to help you more effectively.

Expected wait time: {estimated_wait}

Your inquiry is important to us, and we appreciate your patience. A team member will be with you {estimated_wait}.

Reference ID: {message.message_id[:8]}"""

    def _generate_fallback_response(self, message: Message) -> str:
        """Generate a safe fallback response."""
        customer_email = message.payload.customer_email

        # Try to be helpful based on what we know
        intent = message.payload.intent or {}
        intent_type = intent.get("intent", "general_inquiry")

        if intent_type == "order_status":
            return f"""Thank you for your inquiry about your order status.

I apologize that I'm unable to provide specific details right now. For the most accurate and up-to-date information about your order, please:

1. Check your email for order confirmation and tracking details
2. Visit our order tracking page on our website
3. Contact our customer service team at your convenience

We're here to help ensure you have a great experience with us.

Reference ID: {message.message_id[:8]}"""

        elif intent_type in ["refund_request", "billing_inquiry"]:
            return f"""Thank you for contacting us regarding your billing inquiry.

I want to make sure you receive accurate information about your account. Our billing specialists are the best equipped to help you with this matter.

Please contact our customer service team who can:
- Review your account details securely
- Process any necessary adjustments
- Answer all your billing questions

Reference ID: {message.message_id[:8]}"""

        else:
            return f"""Thank you for reaching out to us.

I want to ensure you receive the most helpful and accurate assistance possible. For the best support with your inquiry, please contact our customer service team who can provide personalized help.

Our team is available to assist you and will be happy to address all your questions and concerns.

Reference ID: {message.message_id[:8]}"""

    async def _send_to_next_actor(self, message: Message) -> None:
        """Send message to the next actor in the route."""
        if not message.route.advance():
            # End of route - send to response aggregator
            await self._send_to_response_aggregator(message)
            return

        next_actor = message.route.get_current_actor()
        if next_actor:
            await self._send_to_specific_actor(message, next_actor)
        else:
            self.logger.error(f"No next actor found for message {message.message_id}")
            await self._send_to_response_aggregator(message)

    async def _send_to_specific_actor(self, message: Message, actor_name: str) -> None:
        """Send message to a specific actor."""
        subject = f"ecommerce.support.{actor_name}"
        await self.send_message(subject, message)
        self.logger.info(f"Sent message {message.message_id} to {actor_name}")

    async def _send_to_response_aggregator(self, message: Message) -> None:
        """Send message to response aggregator."""
        subject = "ecommerce.support.response_aggregator"
        await self.send_message(subject, message)
        self.logger.info(f"Sent message {message.message_id} to response aggregator")

    async def _handle_critical_error(self, message: Message, error: str) -> None:
        """Handle critical errors in escalation router itself."""
        self.logger.critical(f"Critical escalation error for message {message.message_id}: {error}")

        message.add_error("critical_escalation_error", error, self.name)

        # Generate emergency fallback response
        emergency_response = f"""We apologize for the technical difficulty.

Please contact our customer service team directly for immediate assistance.

Reference ID: {message.message_id[:8]}
Error ID: {datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}"""

        message.payload.response = emergency_response
        message.metadata["emergency_fallback"] = True

        await self._send_to_response_aggregator(message)


if __name__ == "__main__":
    import asyncio

    async def main():
        router = EscalationRouter()
        await router.start()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await router.stop()

    asyncio.run(main())
