"""
Mock Services module for the E-commerce Support Agent.

This package provides mock API services that simulate external systems
for testing and demonstration of the Actor Mesh Demo system.
"""

from .customer_api import MockCustomerAPI, get_customer_api
from .orders_api import MockOrdersAPI, get_orders_api
from .tracking_api import MockTrackingAPI, get_tracking_api

__all__ = [
    "MockCustomerAPI",
    "get_customer_api",
    "MockOrdersAPI",
    "get_orders_api",
    "MockTrackingAPI",
    "get_tracking_api",
]
