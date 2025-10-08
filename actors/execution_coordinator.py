"""
Execution Coordinator Actor for the Actor Mesh Demo.

This actor coordinates and executes approved actions by calling various APIs
and services based on the action plan generated in previous processing steps.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from models.message import MessagePayload

from actors.base import ProcessorActor


class ExecutionCoordinator(ProcessorActor):
    """
    Processor actor that executes approved actions via API calls.

    Takes action items from the enriched message payload and executes them
    by calling appropriate mock APIs (Customer, Orders, Tracking).
    """

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        customer_api_url: str = "http://localhost:8001",
        orders_api_url: str = "http://localhost:8002",
        tracking_api_url: str = "http://localhost:8003",
    ):
        """Initialize the Execution Coordinator actor."""
        super().__init__("execution_coordinator", nats_url)

        self.customer_api_url = customer_api_url
        self.orders_api_url = orders_api_url
        self.tracking_api_url = tracking_api_url

        # HTTP client configuration
        self.timeout = 15.0
        self.max_retries = 2

        # Action handlers mapping
        self.action_handlers = {
            "check_order_status": self._check_order_status,
            "provide_tracking_info": self._provide_tracking_info,
            "expedite_order": self._expedite_order,
            "expedite_delivery": self._expedite_delivery,
            "process_return": self._process_return,
            "process_refund": self._process_refund,
            "cancel_order": self._cancel_order,
            "update_delivery_address": self._update_delivery_address,
            "add_customer_note": self._add_customer_note,
            "add_order_note": self._add_order_note,
            "update_customer_tier": self._update_customer_tier,
            "generate_return_label": self._generate_return_label,
            "contact_carrier": self._contact_carrier,
            "schedule_callback": self._schedule_callback,
            "escalate_to_supervisor": self._escalate_to_supervisor,
        }

        # Execution limits for safety
        self.execution_limits = {
            "max_refund_amount": 500.0,
            "max_actions_per_message": 5,
            "restricted_actions": ["process_refund", "cancel_order", "update_customer_tier"],
        }

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Execute approved actions based on the message payload.

        Args:
            payload: Message payload with action items and context

        Returns:
            Dictionary with execution results
        """
        try:
            # Extract action items from response metadata or default actions
            action_items = self._extract_action_items(payload)

            if not action_items:
                self.logger.info("No action items to execute")
                return {
                    "execution_status": "completed",
                    "actions_executed": [],
                    "message": "No actions required",
                }

            # Validate and filter actions
            validated_actions = self._validate_actions(action_items, payload)

            # Execute actions
            execution_results = await self._execute_actions(validated_actions, payload)

            # Summarize results
            summary = self._summarize_execution(execution_results)

            self.logger.info(f"Executed {len(execution_results)} actions with status: {summary['overall_status']}")

            return {
                "execution_status": summary["overall_status"],
                "actions_executed": execution_results,
                "summary": summary,
                "executed_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Error in execution coordination: {e}")
            return {
                "execution_status": "error",
                "actions_executed": [],
                "error": str(e),
                "executed_at": datetime.utcnow().isoformat(),
            }

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with execution results."""
        payload.execution_result = result

    def _extract_action_items(self, payload: MessagePayload) -> List[str]:
        """Extract action items from the payload."""
        action_items = []

        # Check response metadata for action items
        if payload.response and isinstance(payload.response, dict):
            response_metadata = payload.response.get("metadata", {})
            if response_metadata:
                action_items.extend(response_metadata.get("action_items", []))

        # Check for actions in intent analysis
        if payload.intent and "action_items" in payload.intent:
            action_items.extend(payload.intent["action_items"])

        # Infer actions from intent category if no explicit actions
        if not action_items and payload.intent:
            intent_category = payload.intent.get("intent", {}).get("category")
            action_items = self._infer_actions_from_intent(intent_category)

        # Remove duplicates while preserving order
        seen = set()
        unique_actions = []
        for action in action_items:
            if action not in seen:
                seen.add(action)
                unique_actions.append(action)

        return unique_actions

    def _infer_actions_from_intent(self, intent_category: str) -> List[str]:
        """Infer default actions based on intent category."""
        intent_actions = {
            "order_inquiry": ["check_order_status", "provide_tracking_info"],
            "delivery_issue": ["provide_tracking_info", "contact_carrier"],
            "product_complaint": ["add_customer_note", "add_order_note"],
            "return_request": ["generate_return_label", "process_return"],
            "cancellation_request": ["cancel_order"],
            "billing_question": ["add_customer_note"],
            "escalation_request": ["escalate_to_supervisor"],
        }

        return intent_actions.get(intent_category, ["add_customer_note"])

    def _validate_actions(self, action_items: List[str], payload: MessagePayload) -> List[str]:
        """Validate actions against safety limits and policies."""
        validated_actions = []

        # Check action limit
        if len(action_items) > self.execution_limits["max_actions_per_message"]:
            self.logger.warning(
                f"Too many actions requested: {len(action_items)}, limiting to {self.execution_limits['max_actions_per_message']}"
            )
            action_items = action_items[: self.execution_limits["max_actions_per_message"]]

        # Validate each action
        for action in action_items:
            if action in self.action_handlers:
                # Check if action is restricted and needs approval
                if action in self.execution_limits["restricted_actions"]:
                    # Check if we have approval indicators
                    if self._has_action_approval(action, payload):
                        validated_actions.append(action)
                    else:
                        self.logger.warning(f"Restricted action {action} requires approval, skipping")
                else:
                    validated_actions.append(action)
            else:
                self.logger.warning(f"Unknown action: {action}")

        return validated_actions

    def _has_action_approval(self, action: str, payload: MessagePayload) -> bool:
        """Check if a restricted action has appropriate approval."""
        # For demo purposes, we'll allow restricted actions for high-tier customers
        # or when there's high confidence in the analysis

        customer_context = getattr(payload, "context", {}).get("customer_context", {})
        customer_tier = customer_context.get("summary", {}).get("customer_tier", "standard")

        # Allow for premium/VIP customers
        if customer_tier in ["premium", "vip"]:
            return True

        # Allow for high confidence intent analysis
        intent_confidence = getattr(payload, "intent", {}).get("confidence", 0.0)
        if intent_confidence > 0.8:
            return True

        # Allow for specific high-urgency scenarios
        urgency_level = getattr(payload, "sentiment", {}).get("urgency", {}).get("level", "low")
        if urgency_level == "high":
            return True

        return False

    async def _execute_actions(self, actions: List[str], payload: MessagePayload) -> List[Dict[str, Any]]:
        """Execute the validated actions."""
        results = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for action in actions:
                try:
                    handler = self.action_handlers.get(action)
                    if handler:
                        result = await handler(client, payload)
                        result["action"] = action
                        results.append(result)
                    else:
                        results.append(
                            {
                                "action": action,
                                "status": "error",
                                "message": "No handler found for action",
                            }
                        )

                except Exception as e:
                    self.logger.error(f"Error executing action {action}: {e}")
                    results.append(
                        {
                            "action": action,
                            "status": "error",
                            "message": str(e),
                        }
                    )

        return results

    def _summarize_execution(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize execution results."""
        total_actions = len(results)
        successful_actions = len([r for r in results if r.get("status") == "success"])
        failed_actions = len([r for r in results if r.get("status") == "error"])

        if total_actions == 0:
            overall_status = "no_actions"
        elif failed_actions == 0:
            overall_status = "success"
        elif successful_actions == 0:
            overall_status = "failed"
        else:
            overall_status = "partial_success"

        return {
            "overall_status": overall_status,
            "total_actions": total_actions,
            "successful_actions": successful_actions,
            "failed_actions": failed_actions,
            "success_rate": successful_actions / total_actions if total_actions > 0 else 0.0,
        }

    # Action Handler Methods

    async def _check_order_status(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Check order status via Orders API."""
        try:
            # Extract order info from entities or context
            order_id = self._extract_order_id(payload)

            if not order_id:
                return {
                    "status": "error",
                    "message": "No order ID found to check status",
                }

            url = f"{self.orders_api_url}/orders/{order_id}"
            response = await client.get(url)

            if response.status_code == 200:
                order_data = response.json()
                return {
                    "status": "success",
                    "message": f"Order {order_id} status: {order_data.get('status', 'unknown')}",
                    "data": {
                        "order_id": order_id,
                        "order_status": order_data.get("status"),
                        "tracking_number": order_data.get("tracking_number"),
                    },
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to retrieve order status: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error checking order status: {str(e)}",
            }

    async def _provide_tracking_info(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Provide tracking information via Tracking API."""
        try:
            tracking_number = self._extract_tracking_number(payload)

            if not tracking_number:
                return {
                    "status": "error",
                    "message": "No tracking number found",
                }

            url = f"{self.tracking_api_url}/tracking/{tracking_number}"
            response = await client.get(url)

            if response.status_code == 200:
                tracking_data = response.json()
                return {
                    "status": "success",
                    "message": f"Tracking info for {tracking_number}: {tracking_data.get('current_status', 'unknown')}",
                    "data": {
                        "tracking_number": tracking_number,
                        "current_status": tracking_data.get("current_status"),
                        "estimated_delivery": tracking_data.get("estimated_delivery"),
                    },
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to retrieve tracking info: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error retrieving tracking info: {str(e)}",
            }

    async def _expedite_order(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Expedite an order via Orders API."""
        try:
            order_id = self._extract_order_id(payload)

            if not order_id:
                return {
                    "status": "error",
                    "message": "No order ID found to expedite",
                }

            url = f"{self.orders_api_url}/orders/{order_id}/expedite"
            data = {"expedited_by": "support_agent"}

            response = await client.post(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Order {order_id} has been expedited",
                    "data": {"order_id": order_id, "expedited": True},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to expedite order: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error expediting order: {str(e)}",
            }

    async def _expedite_delivery(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Expedite delivery via Tracking API."""
        try:
            tracking_number = self._extract_tracking_number(payload)

            if not tracking_number:
                return {
                    "status": "error",
                    "message": "No tracking number found to expedite delivery",
                }

            url = f"{self.tracking_api_url}/tracking/{tracking_number}/expedite"
            data = {"service_type": "Express", "expedited_by": "support_agent"}

            response = await client.post(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Delivery for {tracking_number} has been expedited",
                    "data": {"tracking_number": tracking_number, "expedited": True},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to expedite delivery: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error expediting delivery: {str(e)}",
            }

    async def _process_refund(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Process a refund via Orders API."""
        try:
            order_id = self._extract_order_id(payload)

            if not order_id:
                return {
                    "status": "error",
                    "message": "No order ID found for refund processing",
                }

            # For safety, we'll process a partial refund or standard amount
            refund_amount = 50.0  # Default refund amount for demo

            url = f"{self.orders_api_url}/orders/{order_id}/refund"
            data = {"amount": refund_amount, "reason": "Customer service adjustment", "processed_by": "support_agent"}

            response = await client.post(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Refund of ${refund_amount} processed for order {order_id}",
                    "data": {"order_id": order_id, "refund_amount": refund_amount},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to process refund: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error processing refund: {str(e)}",
            }

    async def _cancel_order(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Cancel an order via Orders API."""
        try:
            order_id = self._extract_order_id(payload)

            if not order_id:
                return {
                    "status": "error",
                    "message": "No order ID found for cancellation",
                }

            url = f"{self.orders_api_url}/orders/{order_id}/cancel"
            data = {"cancelled_by": "support_agent", "reason": "Customer request"}

            response = await client.post(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Order {order_id} has been cancelled",
                    "data": {"order_id": order_id, "cancelled": True},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to cancel order: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error cancelling order: {str(e)}",
            }

    async def _add_customer_note(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Add a note to customer record via Customer API."""
        try:
            customer_context = getattr(payload, "context", {}).get("customer_context", {})
            customer_id = customer_context.get("profile", {}).get("customer_id")

            if not customer_id:
                return {
                    "status": "error",
                    "message": "No customer ID found to add note",
                }

            note = f"Support interaction: {payload.customer_message[:100]}..."

            url = f"{self.customer_api_url}/customers/{customer_id}/notes"
            data = {"note": note, "agent_id": "support_agent"}

            response = await client.post(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Note added to customer {customer_id} record",
                    "data": {"customer_id": customer_id, "note_added": True},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to add customer note: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error adding customer note: {str(e)}",
            }

    async def _add_order_note(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Add a note to order record via Orders API."""
        try:
            order_id = self._extract_order_id(payload)

            if not order_id:
                return {
                    "status": "error",
                    "message": "No order ID found to add note",
                }

            note = f"Customer inquiry: {payload.customer_message[:100]}..."

            url = f"{self.orders_api_url}/orders/{order_id}/notes"
            data = {"note": note, "added_by": "support_agent"}

            response = await client.post(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Note added to order {order_id}",
                    "data": {"order_id": order_id, "note_added": True},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to add order note: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error adding order note: {str(e)}",
            }

    # Placeholder action handlers for actions that don't have direct API implementations

    async def _generate_return_label(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Generate return label (simulated)."""
        return {
            "status": "success",
            "message": "Return label generated and sent to customer email",
            "data": {"return_label_id": f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}"},
        }

    async def _contact_carrier(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Contact carrier for delivery issues (simulated)."""
        return {
            "status": "success",
            "message": "Carrier has been contacted regarding delivery issue",
            "data": {"contact_initiated": True},
        }

    async def _schedule_callback(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Schedule callback for customer (simulated)."""
        return {
            "status": "success",
            "message": "Callback scheduled within 24 hours",
            "data": {"callback_scheduled": True},
        }

    async def _escalate_to_supervisor(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Escalate to supervisor (simulated)."""
        return {
            "status": "success",
            "message": "Case escalated to supervisor for review",
            "data": {"escalated": True, "escalation_id": f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}"},
        }

    async def _update_customer_tier(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Update customer tier via Customer API."""
        try:
            customer_context = getattr(payload, "context", {}).get("customer_context", {})
            customer_id = customer_context.get("profile", {}).get("customer_id")
            current_tier = customer_context.get("summary", {}).get("customer_tier", "standard")

            if not customer_id:
                return {
                    "status": "error",
                    "message": "No customer ID found for tier update",
                }

            # Upgrade tier as compensation
            new_tier = "premium" if current_tier == "standard" else "vip"

            url = f"{self.customer_api_url}/customers/{customer_id}/tier"
            data = {"tier": new_tier}

            response = await client.put(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Customer tier upgraded from {current_tier} to {new_tier}",
                    "data": {"customer_id": customer_id, "old_tier": current_tier, "new_tier": new_tier},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to update customer tier: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error updating customer tier: {str(e)}",
            }

    async def _update_delivery_address(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Update delivery address via Tracking API."""
        try:
            tracking_number = self._extract_tracking_number(payload)

            if not tracking_number:
                return {
                    "status": "error",
                    "message": "No tracking number found for address update",
                }

            # For demo, we'll simulate address correction
            url = f"{self.tracking_api_url}/tracking/{tracking_number}/address"
            data = {
                "address": {"street": "123 Corrected St", "city": "Anytown", "state": "CA", "zip_code": "12345"},
                "updated_by": "support_agent",
            }

            response = await client.put(url, json=data)

            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": f"Delivery address updated for {tracking_number}",
                    "data": {"tracking_number": tracking_number, "address_updated": True},
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to update delivery address: {response.status_code}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error updating delivery address: {str(e)}",
            }

    async def _process_return(self, client: httpx.AsyncClient, payload: MessagePayload) -> Dict[str, Any]:
        """Process return request (combines several steps)."""
        # This action combines generating return label and updating order status
        results = []

        # Generate return label
        label_result = await self._generate_return_label(client, payload)
        results.append(label_result)

        # Add note to order
        note_result = await self._add_order_note(client, payload)
        results.append(note_result)

        successful_steps = len([r for r in results if r.get("status") == "success"])

        return {
            "status": "success" if successful_steps > 0 else "error",
            "message": f"Return process initiated ({successful_steps}/2 steps completed)",
            "data": {"steps_completed": successful_steps, "return_initiated": successful_steps > 0},
        }

    # Helper methods for extracting information from payload

    def _extract_order_id(self, payload: MessagePayload) -> Optional[str]:
        """Extract order ID from entities or context."""
        # Check entities from intent analysis
        if payload.intent and "entities" in payload.intent:
            for entity in payload.intent["entities"]:
                if isinstance(entity, dict) and entity.get("type") == "order_number":
                    return entity.get("value")

        # Check customer context for recent orders
        context = getattr(payload, "context", {}).get("customer_context", {})
        orders = context.get("orders", [])
        if orders:
            return orders[0].get("order_id")  # Return most recent order

        return None

    def _extract_tracking_number(self, payload: MessagePayload) -> Optional[str]:
        """Extract tracking number from entities or context."""
        # Check entities from intent analysis
        if payload.intent and "entities" in payload.intent:
            for entity in payload.intent["entities"]:
                if isinstance(entity, dict) and entity.get("type") == "tracking_number":
                    return entity.get("value")

        # Check customer context for recent orders with tracking
        context = getattr(payload, "context", {}).get("customer_context", {})
        orders = context.get("orders", [])
        for order in orders:
            tracking_number = order.get("tracking_number")
            if tracking_number:
                return tracking_number

        return None


# Factory function for creating the actor
def create_execution_coordinator(
    nats_url: str = "nats://localhost:4222",
    customer_api_url: str = "http://localhost:8001",
    orders_api_url: str = "http://localhost:8002",
    tracking_api_url: str = "http://localhost:8003",
) -> ExecutionCoordinator:
    """Create an ExecutionCoordinator actor instance."""
    return ExecutionCoordinator(nats_url, customer_api_url, orders_api_url, tracking_api_url)


# Main execution for standalone testing
async def main():
    """Main function for testing the execution coordinator."""
    logging.basicConfig(level=logging.INFO)

    # Create and start the actor
    coordinator = ExecutionCoordinator()

    try:
        await coordinator.start()
        print("Execution Coordinator started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await coordinator.stop()


if __name__ == "__main__":
    asyncio.run(main())
