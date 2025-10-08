"""
Models module for the E-commerce Support Agent.

This package contains data models and message structures used throughout
the Actor Mesh Demo system.
"""

from .message import (
    Message,
    MessagePayload,
    Route,
    StandardRoutes,
    create_error_message,
    create_support_message,
)

__all__ = [
    "Message",
    "MessagePayload",
    "Route",
    "StandardRoutes",
    "create_error_message",
    "create_support_message",
]
