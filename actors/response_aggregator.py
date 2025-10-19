"""
Response Aggregator Actor for the E-commerce Support Agent.

This actor collects final responses from the processing pipeline and delivers
them back to the API Gateway or other response handlers.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from models.message import Message, MessagePayload

from actors.base import BaseActor


class ResponseAggregator(BaseActor):
    """
    Actor that aggregates final responses and delivers them to requesters.

    The ResponseAggregator is the final step in the processing pipeline,
    collecting enriched messages with responses and routing them back
    to the appropriate response handler (typically the API Gateway).
    """

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        super().__init__("response_aggregator", nats_url)
        self.logger = logging.getLogger("actor.response_aggregator")

        # Response delivery configuration
        self.default_response_subject = "ecommerce.support.gateway.response"
        self.delivery_timeout = 5.0

        # Statistics tracking
        self.responses_processed = 0
        self.responses_delivered = 0
        self.delivery_failures = 0

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Process final response and deliver to appropriate handler.

        Args:
            payload: The message payload with final response to aggregate and deliver

        Returns:
            None as this is the final step in the pipeline
        """
        try:
            # We need access to the full message for routing, but base class only provides payload
            # This is a limitation of the current architecture - we'll work around it

            self.logger.info(f"Processing final response for customer: {payload.customer_email}")

            # Validate payload has response
            if not payload.response:
                self.logger.warning(f"Payload has no response - generating fallback")
                payload.response = self._generate_fallback_response_from_payload(payload)

            # Since we don't have access to the full message, we'll create a response data structure
            # and publish it directly to the gateway response subject
            response_data = self._prepare_response_data_from_payload(payload)

            # Deliver response directly
            await self._deliver_response_from_payload(response_data)

            # Update statistics
            self.responses_processed += 1
            self.responses_delivered += 1

            self.logger.info(f"Successfully delivered response for customer {payload.customer_email}")

            # Return None as this is the final step
            return None

        except Exception as e:
            self.delivery_failures += 1
            self.logger.error(f"Error aggregating response for customer {payload.customer_email}: {str(e)}")
            await self._handle_delivery_error_from_payload(payload, str(e))
            return None

    def _prepare_response_data_from_payload(self, payload: MessagePayload) -> Dict[str, Any]:
        """
        Prepare response data for delivery from payload only.

        Args:
            payload: The processed message payload

        Returns:
            Response data dictionary
        """
        # Extract key response information
        response_data = {
            "message_id": "unknown",  # Not available from payload
            "session_id": "unknown",  # Not available from payload
            "response": payload.response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add processing metadata
        metadata = {
            "processing_complete": True,
            "route_completed": True,  # Assume complete since we're at the final step
        }

        # Add enrichment summary
        enrichments = self._summarize_enrichments_from_payload(payload)
        if enrichments:
            metadata["enrichments"] = enrichments

        # Add error information if present
        if payload.error:
            metadata["error_occurred"] = True
            metadata["error_type"] = payload.error.get("type")
            metadata["recovery_attempts"] = len(payload.recovery_log)

        # Add execution results if present
        if payload.execution_result:
            metadata["actions_executed"] = True
            execution_result = payload.execution_result
            metadata["execution_summary"] = {
                "success": execution_result.get("success", False),
                "actions_count": len(execution_result.get("actions", [])),
            }

        # Add guardrail information
        if payload.guardrail_check:
            metadata["guardrails"] = {
                "passed": payload.guardrail_check.get("passed", True),
                "checks_performed": len(payload.guardrail_check.get("checks", [])),
            }

        # Add escalation information if present
        context = payload.context or {}
        if "escalation" in context:
            metadata["escalated"] = True
            metadata["escalation_info"] = context["escalation"]

        response_data["metadata"] = metadata

        return response_data

    def _summarize_enrichments_from_payload(self, payload: MessagePayload) -> Dict[str, bool]:
        """Create summary of enrichments applied to the payload."""
        enrichments = {}

        if payload.sentiment:
            enrichments["sentiment_analysis"] = True

        if payload.intent:
            enrichments["intent_classification"] = True

        if payload.context:
            enrichments["context_retrieval"] = True

        if payload.api_data:
            enrichments["api_data_gathered"] = True

        if payload.action_plan:
            enrichments["action_planning"] = True

        if payload.guardrail_check:
            enrichments["guardrail_validation"] = True

        if payload.execution_result:
            enrichments["action_execution"] = True

        return enrichments

    async def _deliver_response_from_payload(self, response_data: Dict[str, Any]) -> None:
        """
        Deliver response to the gateway (default delivery target).

        Args:
            response_data: Prepared response data
        """
        # Always deliver to default response subject since we don't have full message context
        delivery_subject = self.default_response_subject

        try:
            # Convert to JSON and publish
            response_json = json.dumps(response_data)
            await self.nc.publish(delivery_subject, response_json.encode())

            self.logger.debug(f"Delivered response to {delivery_subject}")

        except Exception as e:
            self.logger.error(f"Failed to deliver response to {delivery_subject}: {str(e)}")
            raise

    def _get_delivery_subject(self, message: Message) -> str:
        """
        Determine the NATS subject for response delivery.

        Args:
            message: The message being processed

        Returns:
            NATS subject for delivery
        """
        # Check if message has specific delivery instructions
        metadata = message.metadata
        if "response_subject" in metadata:
            return metadata["response_subject"]

        # Check if this is an API request
        if metadata.get("api_request"):
            return self.default_response_subject

        # Check for session-specific delivery
        if message.session_id:
            return f"ecommerce.support.response.session.{message.session_id}"

        # Default delivery
        return self.default_response_subject

    def _generate_fallback_response_from_payload(self, payload: MessagePayload) -> str:
        """
        Generate a fallback response when none exists.

        Args:
            payload: The message payload without a response

        Returns:
            Fallback response text
        """
        self.logger.warning(f"Generating fallback response for customer {payload.customer_email}")

        # Try to create contextual fallback based on what we know
        intent = payload.intent or {}
        intent_type = intent.get("intent", "general_inquiry")

        if intent_type == "order_status":
            return """Thank you for your inquiry about your order.

I apologize that I couldn't retrieve your specific order details at the moment. Please check your email for order confirmation and tracking information, or contact our customer service team for personalized assistance.

We appreciate your business and are here to help."""

        elif intent_type in ["refund_request", "billing_inquiry"]:
            return """Thank you for contacting us about your billing inquiry.

Our customer service team is best equipped to help you with account-specific matters. Please contact them directly, and they'll be happy to review your account and assist you with any billing questions or refund requests.

We value your business and want to ensure you receive the best possible service."""

        else:
            return """Thank you for reaching out to us.

While I wasn't able to provide a specific response to your inquiry, our customer service team is available to assist you with personalized help for any questions or concerns you may have.

We appreciate your patience and look forward to serving you."""

    async def _handle_delivery_error_from_payload(self, payload: MessagePayload, error: str) -> None:
        """
        Handle errors during response delivery.

        Args:
            payload: The payload that failed to deliver
            error: Error description
        """
        self.logger.error(f"Delivery error for customer {payload.customer_email}: {error}")

        # Try alternative delivery methods
        try:
            # Attempt delivery to error subject
            error_subject = "ecommerce.support.error.delivery"
            error_data = {
                "customer_email": payload.customer_email,
                "error": error,
                "original_response": payload.response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            error_json = json.dumps(error_data)
            await self.nc.publish(error_subject, error_json.encode())

            self.logger.info(f"Sent delivery error notification for customer {payload.customer_email}")

        except Exception as fallback_error:
            self.logger.critical(f"Failed to send error notification: {fallback_error}")

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """
        Override to prevent enrichment - this is the final step.

        Args:
            payload: The message payload (not modified)
            result: Processing result (ignored)
        """
        # No enrichment needed - this is the final step in the pipeline
        pass

    async def _route_to_next(self, message: Message) -> None:
        """Override routing to deliver response to gateway instead of continuing pipeline."""
        try:
            self.logger.info(f"Delivering final response for message {message.message_id}")

            # Validate message has response
            if not message.payload.response:
                self.logger.warning(f"Message {message.message_id} has no response - generating fallback")
                message.payload.response = self._generate_fallback_response(message)

            # Prepare response data
            response_data = self._prepare_response_data(message)

            # Deliver response to gateway
            await self._deliver_response(message, response_data)

            # Update statistics
            self.responses_delivered += 1

            self.logger.info(f"Successfully delivered response for message {message.message_id}")

        except Exception as e:
            self.delivery_failures += 1
            self.logger.error(f"Error delivering response for message {message.message_id}: {str(e)}")
            await self._handle_delivery_error(message, str(e))

    def _prepare_response_data(self, message: Message) -> Dict[str, Any]:
        """
        Prepare response data for delivery.

        Args:
            message: The processed message

        Returns:
            Response data dictionary
        """
        # Extract key response information
        response_data = {
            "message_id": message.message_id,
            "session_id": message.session_id,
            "response": message.payload.response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add processing metadata
        metadata = {
            "processing_complete": True,
            "route_completed": message.route.is_complete(),
            "total_steps": len(message.route.steps),
            "steps_completed": message.route.current_step + 1,
        }

        # Add enrichment summary
        enrichments = self._summarize_enrichments(message)
        if enrichments:
            metadata["enrichments"] = enrichments

        # Add error information if present
        if message.payload.error:
            metadata["error_occurred"] = True
            metadata["error_type"] = message.payload.error.get("type")
            metadata["recovery_attempts"] = len(message.payload.recovery_log)

        # Add execution results if present
        if message.payload.execution_result:
            metadata["actions_executed"] = True
            execution_result = message.payload.execution_result
            metadata["execution_summary"] = {
                "success": execution_result.get("success", False),
                "actions_count": len(execution_result.get("actions", [])),
            }

        # Add guardrail information
        if message.payload.guardrail_check:
            metadata["guardrails"] = {
                "passed": message.payload.guardrail_check.get("passed", True),
                "checks_performed": len(message.payload.guardrail_check.get("checks", [])),
            }

        # Add escalation information if present
        context = message.payload.context or {}
        if "escalation" in context:
            metadata["escalated"] = True
            metadata["escalation_info"] = context["escalation"]

        # Add performance information
        if "gateway_timestamp" in message.metadata:
            try:
                start_time = datetime.fromisoformat(message.metadata["gateway_timestamp"])
                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                metadata["total_processing_time"] = processing_time
            except (ValueError, KeyError):
                pass

        # Add fallback information if used
        if message.metadata.get("fallback_used"):
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = message.metadata.get("fallback_reason")

        response_data["metadata"] = metadata

        return response_data

    def _summarize_enrichments(self, message: Message) -> Dict[str, bool]:
        """Create summary of enrichments applied to the message."""
        enrichments = {}

        if message.payload.sentiment:
            enrichments["sentiment_analysis"] = True

        if message.payload.intent:
            enrichments["intent_classification"] = True

        if message.payload.context:
            enrichments["context_retrieval"] = True

        if message.payload.api_data:
            enrichments["api_data_gathered"] = True

        if message.payload.action_plan:
            enrichments["action_planning"] = True

        if message.payload.guardrail_check:
            enrichments["guardrail_validation"] = True

        if message.payload.execution_result:
            enrichments["action_execution"] = True

        return enrichments

    async def _deliver_response(self, message: Message, response_data: Dict[str, Any]) -> None:
        """
        Deliver response to the appropriate handler.

        Args:
            message: The original message
            response_data: Prepared response data
        """
        # Determine delivery target
        delivery_subject = self._get_delivery_subject(message)

        try:
            # Convert to JSON and publish
            response_json = json.dumps(response_data)
            await self.nc.publish(delivery_subject, response_json.encode())

            self.logger.debug(f"Delivered response to {delivery_subject}")

        except Exception as e:
            self.logger.error(f"Failed to deliver response to {delivery_subject}: {str(e)}")
            raise

    def _generate_fallback_response(self, message: Message) -> str:
        """
        Generate a fallback response when none exists.

        Args:
            message: The message without a response

        Returns:
            Fallback response text
        """
        self.logger.warning(f"Generating fallback response for message {message.message_id}")

        # Try to create contextual fallback based on what we know
        intent = message.payload.intent or {}
        intent_type = intent.get("intent", "general_inquiry")

        if intent_type == "order_status":
            return """Thank you for your inquiry about your order.

I apologize that I couldn't retrieve your specific order details at the moment. Please check your email for order confirmation and tracking information, or contact our customer service team for personalized assistance.

We appreciate your business and are here to help."""

        elif intent_type in ["refund_request", "billing_inquiry"]:
            return """Thank you for contacting us about your billing inquiry.

Our customer service team is best equipped to help you with account-specific matters. Please contact them directly, and they'll be happy to review your account and assist you with any billing questions or refund requests.

We value your business and want to ensure you receive the best possible service."""

        else:
            return """Thank you for reaching out to us.

While I wasn't able to provide a specific response to your inquiry, our customer service team is available to assist you with personalized help for any questions or concerns you may have.

We appreciate your patience and look forward to serving you."""

    async def _handle_delivery_error(self, message: Message, error: str) -> None:
        """
        Handle errors during response delivery.

        Args:
            message: The message that failed to deliver
            error: Error description
        """
        self.logger.error(f"Delivery error for message {message.message_id}: {error}")

        # Add error to message
        message.add_error("response_delivery_error", error, self.name)

        # Try alternative delivery methods
        try:
            # Attempt delivery to error subject
            error_subject = "ecommerce.support.error.delivery"
            error_data = {
                "message_id": message.message_id,
                "session_id": message.session_id,
                "error": error,
                "original_response": message.payload.response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            error_json = json.dumps(error_data)
            await self.nc.publish(error_subject, error_json.encode())

            self.logger.info(f"Sent delivery error notification for message {message.message_id}")

        except Exception as fallback_error:
            self.logger.critical(f"Failed to send error notification: {fallback_error}")

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get response aggregator statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "responses_processed": self.responses_processed,
            "responses_delivered": self.responses_delivered,
            "delivery_failures": self.delivery_failures,
            "delivery_success_rate": (self.responses_delivered / max(self.responses_processed, 1) * 100),
            "pending_responses": 0,  # This actor doesn't queue responses
            "uptime": getattr(self, "_start_time", datetime.now(timezone.utc)).isoformat(),
        }


def create_response_aggregator(nats_url: str = "nats://localhost:4222") -> ResponseAggregator:
    """
    Factory function to create a ResponseAggregator instance.

    Args:
        nats_url: NATS server URL

    Returns:
        Configured ResponseAggregator instance
    """
    return ResponseAggregator(nats_url=nats_url)


if __name__ == "__main__":
    import asyncio

    async def main():
        aggregator = ResponseAggregator()
        await aggregator.start()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await aggregator.stop()

    asyncio.run(main())
