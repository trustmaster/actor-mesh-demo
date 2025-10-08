"""
Decision Router Actor for the E-commerce Support Agent.

This router makes intelligent routing decisions based on sentiment analysis,
intent classification, and context data to direct messages to appropriate
processing pipelines.
"""

import logging
from typing import Any, Dict, Optional

from models.message import Message, MessagePayload

from actors.base import RouterActor


class DecisionRouter(RouterActor):
    """
    Smart router that makes routing decisions based on enriched message content.

    The DecisionRouter analyzes sentiment, intent, and context to determine
    the optimal processing path for each customer message.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        super().__init__("decision_router", nats_url)
        self.logger = logging.getLogger("actor.decision_router")

    async def route_message(self, message: Message) -> None:
        """
        Make intelligent routing decisions based on message content.

        Args:
            message: The enriched message to route
        """
        try:
            self.logger.info(f"Processing routing decision for message {message.message_id}")

            # Extract enrichment data
            sentiment = message.payload.sentiment or {}
            intent = message.payload.intent or {}
            context = message.payload.context or {}

            # Log current enrichments
            self.logger.debug(f"Sentiment: {sentiment}")
            self.logger.debug(f"Intent: {intent}")
            self.logger.debug(f"Context: {context}")

            # Make routing decisions
            routing_changes = self._make_routing_decisions(message, sentiment, intent, context)

            if routing_changes:
                self.logger.info(f"Applied routing changes: {routing_changes}")

            # Continue with the modified route
            await self._send_to_next_actor(message)

        except Exception as e:
            self.logger.error(f"Error in routing decision: {str(e)}")
            await self._handle_routing_error(message, str(e))

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Process method required by BaseActor - not used for router actors.

        Args:
            payload: The message payload to process

        Returns:
            None as router actors handle routing directly
        """
        return None

    def _make_routing_decisions(
        self, message: Message, sentiment: Dict[str, Any], intent: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply routing logic based on enrichment data.

        Returns:
            Dict describing the routing changes made
        """
        changes = {}

        # 1. Critical escalation check
        if self._should_escalate_immediately(sentiment, intent, context):
            changes["immediate_escalation"] = True
            message.route.steps = ["escalation_router", "response_aggregator"]
            message.route.current_step = 0
            return changes

        # 2. High-priority processing
        if self._needs_priority_processing(sentiment, intent):
            changes["priority_processing"] = True
            self._insert_priority_steps(message)

        # 3. Action execution requirements
        if self._needs_action_execution(intent, context):
            changes["action_execution"] = True
            self._ensure_execution_coordinator(message)

        # 4. Low confidence handling
        if self._has_low_confidence(intent):
            changes["low_confidence"] = True
            self._add_human_review(message)

        # 5. Complex query routing
        if self._is_complex_query(intent, context):
            changes["complex_processing"] = True
            self._add_enhanced_processing(message)

        return changes

    def _should_escalate_immediately(
        self, sentiment: Dict[str, Any], intent: Dict[str, Any], context: Dict[str, Any]
    ) -> bool:
        """Check if message should be escalated immediately."""

        # Critical sentiment
        if sentiment.get("urgency") == "critical":
            return True

        # Very angry customer
        if sentiment.get("sentiment") == "negative" and sentiment.get("intensity", 0) > 0.8:
            return True

        # Legal threats or complaints
        intent_type = intent.get("intent", "")
        if intent_type in ["legal_threat", "formal_complaint", "regulatory_complaint"]:
            return True

        # VIP customer issues
        customer_tier = context.get("customer", {}).get("tier", "")
        if customer_tier == "VIP" and sentiment.get("urgency") in ["high", "critical"]:
            return True

        return False

    def _needs_priority_processing(self, sentiment: Dict[str, Any], intent: Dict[str, Any]) -> bool:
        """Check if message needs priority processing."""

        # High urgency
        if sentiment.get("urgency") == "high":
            return True

        # Billing or refund requests
        intent_type = intent.get("intent", "")
        if intent_type in ["billing_inquiry", "refund_request", "payment_issue"]:
            return True

        return False

    def _needs_action_execution(self, intent: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if message requires action execution."""

        intent_type = intent.get("intent", "")
        actionable_intents = [
            "refund_request",
            "order_modification",
            "shipping_change",
            "billing_update",
            "account_update",
            "order_cancellation",
        ]

        return intent_type in actionable_intents

    def _has_low_confidence(self, intent: Dict[str, Any]) -> bool:
        """Check if intent analysis has low confidence."""
        return intent.get("confidence", 1.0) < 0.6

    def _is_complex_query(self, intent: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if query is complex and needs enhanced processing."""

        intent_type = intent.get("intent", "")
        complex_intents = ["technical_support", "product_compatibility", "bulk_order"]

        # Multiple orders or complex history
        orders = context.get("orders", [])
        if len(orders) > 5:
            return True

        return intent_type in complex_intents

    def _insert_priority_steps(self, message: Message) -> None:
        """Insert priority processing steps."""
        current_pos = message.route.current_step

        # Insert after current step if not already there
        next_steps = message.route.steps[current_pos + 1 :]
        if "response_generator" not in next_steps[:2]:
            # Fast-track to response generation
            message.route.steps.insert(current_pos + 1, "response_generator")

    def _ensure_execution_coordinator(self, message: Message) -> None:
        """Ensure execution coordinator is in the pipeline."""
        if "execution_coordinator" not in message.route.steps:
            # Insert before response generation
            response_idx = self._find_step_index(message.route.steps, "response_generator")
            if response_idx is not None:
                message.route.steps.insert(response_idx, "execution_coordinator")
            else:
                message.route.steps.append("execution_coordinator")

    def _add_human_review(self, message: Message) -> None:
        """Add human review step for low confidence cases."""
        if "escalation_router" not in message.route.steps:
            # Insert before response aggregator
            aggregator_idx = self._find_step_index(message.route.steps, "response_aggregator")
            if aggregator_idx is not None:
                message.route.steps.insert(aggregator_idx, "escalation_router")
            else:
                message.route.steps.append("escalation_router")

    def _add_enhanced_processing(self, message: Message) -> None:
        """Add enhanced processing for complex queries."""
        # Ensure context retriever is called if not already
        if message.route.current_step < len(message.route.steps):
            remaining_steps = message.route.steps[message.route.current_step + 1 :]
            if "context_retriever" not in remaining_steps:
                message.route.steps.insert(message.route.current_step + 1, "context_retriever")

    def _find_step_index(self, steps: list, step_name: str) -> Optional[int]:
        """Find the index of a step in the route."""
        try:
            return steps.index(step_name)
        except ValueError:
            return None

    async def _send_to_next_actor(self, message: Message) -> None:
        """Send message to the next actor in the route."""
        if not message.route.advance():
            self.logger.warning(f"Message {message.message_id} reached end of route")
            return

        next_actor = message.route.get_current_actor()
        if next_actor:
            subject = f"ecommerce.support.{next_actor}"
            await self.send_message(subject, message)
            self.logger.info(f"Routed message {message.message_id} to {next_actor}")
        else:
            self.logger.error(f"No next actor found for message {message.message_id}")

    async def _handle_routing_error(self, message: Message, error: str) -> None:
        """Handle routing errors by escalating to error handler."""
        self.logger.error(f"Routing error for message {message.message_id}: {error}")

        message.add_error("routing_error", error, self.name)

        # Route to escalation
        if message.route.error_handler:
            subject = f"ecommerce.support.{message.route.error_handler}"
            await self.send_message(subject, message)
        else:
            # Default to escalation router
            subject = "ecommerce.support.escalation_router"
            await self.send_message(subject, message)


if __name__ == "__main__":
    import asyncio

    async def main():
        router = DecisionRouter()
        await router.start()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await router.stop()

    asyncio.run(main())
