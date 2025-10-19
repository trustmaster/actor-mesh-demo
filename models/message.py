"""
Core message protocol models for the Actor Mesh Demo.

This module implements the message structure used for communication between
actors in the e-commerce support agent system.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Route(BaseModel):
    """Routing information for message flow between actors."""

    steps: List[str] = Field(description="List of actor mailbox addresses")
    current_step: int = Field(default=0, description="Current position in the route")
    error_handler: Optional[str] = Field(default=None, description="Error recovery actor")

    def get_current_actor(self) -> Optional[str]:
        """Get the current actor in the route."""
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def get_next_actor(self) -> Optional[str]:
        """Get the next actor in the route."""
        if self.current_step + 1 < len(self.steps):
            return self.steps[self.current_step + 1]
        return None

    def advance(self) -> bool:
        """Advance to the next step. Returns True if successful, False if at end."""
        if self.current_step + 1 < len(self.steps):
            self.current_step += 1
            return True
        return False

    def is_complete(self) -> bool:
        """Check if the route is complete."""
        return self.current_step >= len(self.steps) - 1


class MessagePayload(BaseModel):
    """Content payload that gets enriched as it flows through actors."""

    # Original input (immutable)
    customer_message: str = Field(description="Original customer message")
    customer_email: str = Field(description="Customer email address")

    # Enrichments (appended by actors)
    sentiment: Optional[Dict[str, Any]] = Field(default=None, description="Sentiment analysis results")
    intent: Optional[Dict[str, Any]] = Field(default=None, description="Intent classification results")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Customer context data")
    api_data: Optional[Dict[str, Any]] = Field(default=None, description="External API responses")
    action_plan: Optional[Dict[str, Any]] = Field(default=None, description="Planned actions")
    response: Optional[str] = Field(default=None, description="Generated response text")
    guardrail_check: Optional[Dict[str, Any]] = Field(default=None, description="Guardrail validation results")
    execution_result: Optional[Dict[str, Any]] = Field(default=None, description="Action execution results")

    # Error tracking
    error: Optional[Dict[str, Any]] = Field(default=None, description="Error information")
    recovery_log: List[Dict[str, Any]] = Field(default_factory=list, description="Error recovery attempts")


class Message(BaseModel):
    """Main message structure for actor communication."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique message identifier")
    session_id: str = Field(description="Conversation session identifier")
    route: Route = Field(description="Routing information")
    payload: MessagePayload = Field(description="Message content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Message metadata")

    def __init__(self, **data):
        super().__init__(**data)
        # Add creation timestamp
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = datetime.now(timezone.utc).isoformat()
        if "retry_count" not in self.metadata:
            self.metadata["retry_count"] = 0

    def add_enrichment(self, field: str, data: Dict[str, Any]) -> None:
        """Add enrichment data to the payload."""
        setattr(self.payload, field, data)

    def add_error(self, error_type: str, error_message: str, actor: str) -> None:
        """Add error information to the payload."""
        error_info = {
            "type": error_type,
            "message": error_message,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.payload.error = error_info
        self.payload.recovery_log.append(error_info)

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self.metadata["retry_count"] += 1
        self.metadata["last_retry_at"] = datetime.now(timezone.utc).isoformat()

    def to_nats_subject(self, actor_name: str) -> str:
        """Generate NATS subject for the given actor."""
        return f"ecommerce.support.{actor_name}"


# Standard routes for different message flows
class StandardRoutes:
    """Predefined routes for common workflows."""

    # Complete processing pipeline for API Gateway
    FULL_PROCESSING_PIPELINE = [
        "sentiment_analyzer",
        "intent_analyzer",
        "context_retriever",
        "decision_router",
        "response_generator",
        "guardrail_validator",
        "response_aggregator",
    ]

    @staticmethod
    def complaint_analysis_route() -> Route:
        """Route for analyzing customer complaints."""
        return Route(
            steps=["sentiment_analyzer", "intent_analyzer", "context_retriever", "decision_router"],
            error_handler="escalation_router",
        )

    @staticmethod
    def response_generation_route() -> Route:
        """Route for generating and validating responses."""
        return Route(
            steps=["response_generator", "guardrail_validator", "response_aggregator"],
            error_handler="escalation_router",
        )

    @staticmethod
    def action_execution_route() -> Route:
        """Route for executing approved actions."""
        return Route(steps=["execution_coordinator", "response_aggregator"], error_handler="escalation_router")

    @staticmethod
    def full_support_flow() -> Route:
        """Complete support flow from analysis to response."""
        return Route(
            steps=[
                "sentiment_analyzer",
                "intent_analyzer",
                "context_retriever",
                "decision_router",
                "response_generator",
                "guardrail_validator",
                "response_aggregator",
            ],
            error_handler="escalation_router",
        )


# Message factory functions
def create_support_message(customer_message: str, customer_email: str, session_id: str, route: Route) -> Message:
    """Create a new support message."""
    payload = MessagePayload(customer_message=customer_message, customer_email=customer_email)

    return Message(session_id=session_id, route=route, payload=payload)


def create_error_message(original_message: Message, error_type: str, error_message: str, actor: str) -> Message:
    """Create an error message from a failed message."""
    error_msg = Message(
        session_id=original_message.session_id,
        route=Route(
            steps=[original_message.route.error_handler]
            if original_message.route.error_handler
            else ["escalation_router"],
            current_step=0,
        ),
        payload=original_message.payload,
        metadata=original_message.metadata.copy(),
    )

    error_msg.add_error(error_type, error_message, actor)
    return error_msg
