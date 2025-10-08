"""
Mock Customer API service for the Actor Mesh Demo.

This module provides a mock customer service API that simulates
retrieving customer data, order history, and account information.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class CustomerProfile(BaseModel):
    """Customer profile data structure."""

    customer_id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    account_status: str = "active"  # active, suspended, premium
    tier: str = "standard"  # standard, premium, vip
    registration_date: str
    last_login: Optional[str] = None
    preferences: Dict[str, Any] = {}
    address: Optional[Dict[str, str]] = None


class CustomerOrder(BaseModel):
    """Customer order data structure."""

    order_id: str
    customer_id: str
    status: str  # pending, confirmed, shipped, delivered, cancelled
    total_amount: float
    currency: str = "USD"
    items: List[Dict[str, Any]]
    order_date: str
    estimated_delivery: Optional[str] = None
    tracking_number: Optional[str] = None


class CustomerSupport(BaseModel):
    """Customer support interaction data."""

    interaction_id: str
    customer_id: str
    type: str  # complaint, inquiry, compliment
    status: str  # open, in_progress, resolved, escalated
    priority: str  # low, medium, high, urgent
    subject: str
    description: str
    created_date: str
    resolved_date: Optional[str] = None
    agent_id: Optional[str] = None


class MockCustomerAPI:
    """Mock customer API implementation."""

    def __init__(self):
        """Initialize mock data."""
        self.logger = logging.getLogger("mock_customer_api")

        # Mock customer database
        self.customers: Dict[str, CustomerProfile] = {}
        self.orders: Dict[str, List[CustomerOrder]] = {}
        self.support_history: Dict[str, List[CustomerSupport]] = {}

        # Initialize with sample data
        self._initialize_mock_data()

    def _initialize_mock_data(self):
        """Create sample customer data."""
        # Sample customers
        sample_customers = [
            {
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "phone": "+1-555-0123",
                "tier": "premium",
                "address": {"street": "123 Main St", "city": "Anytown", "state": "CA", "zip": "12345", "country": "US"},
            },
            {
                "email": "jane.smith@example.com",
                "first_name": "Jane",
                "last_name": "Smith",
                "phone": "+1-555-0456",
                "tier": "vip",
                "address": {
                    "street": "456 Oak Ave",
                    "city": "Springfield",
                    "state": "NY",
                    "zip": "67890",
                    "country": "US",
                },
            },
            {
                "email": "bob.wilson@example.com",
                "first_name": "Bob",
                "last_name": "Wilson",
                "tier": "standard",
                "address": {
                    "street": "789 Pine St",
                    "city": "Portland",
                    "state": "OR",
                    "zip": "97201",
                    "country": "US",
                },
            },
        ]

        for customer_data in sample_customers:
            customer_id = str(uuid4())

            # Create customer profile
            customer = CustomerProfile(
                customer_id=customer_id,
                registration_date=(datetime.now() - timedelta(days=365)).isoformat(),
                last_login=datetime.now().isoformat(),
                preferences={"email_notifications": True, "sms_notifications": False, "newsletter": True},
                **customer_data,
            )

            self.customers[customer.email] = customer

            # Create sample orders
            self._create_sample_orders(customer_id, customer.email)

            # Create sample support history
            self._create_sample_support_history(customer_id)

    def _create_sample_orders(self, customer_id: str, email: str):
        """Create sample orders for a customer."""
        orders = []

        # Recent order (delivered)
        orders.append(
            CustomerOrder(
                order_id=f"ORD-{uuid4().hex[:8].upper()}",
                customer_id=customer_id,
                status="delivered",
                total_amount=129.99,
                items=[
                    {"name": "Wireless Headphones", "quantity": 1, "price": 99.99},
                    {"name": "Phone Case", "quantity": 1, "price": 19.99},
                    {"name": "Shipping", "quantity": 1, "price": 9.99},
                ],
                order_date=(datetime.now() - timedelta(days=15)).isoformat(),
                estimated_delivery=(datetime.now() - timedelta(days=12)).isoformat(),
                tracking_number="TRK123456789",
            )
        )

        # Current order (shipped)
        orders.append(
            CustomerOrder(
                order_id=f"ORD-{uuid4().hex[:8].upper()}",
                customer_id=customer_id,
                status="shipped",
                total_amount=259.97,
                items=[
                    {"name": "Laptop Stand", "quantity": 1, "price": 79.99},
                    {"name": "USB Hub", "quantity": 2, "price": 89.99},
                    {"name": "Express Shipping", "quantity": 1, "price": 15.99},
                ],
                order_date=(datetime.now() - timedelta(days=3)).isoformat(),
                estimated_delivery=(datetime.now() + timedelta(days=1)).isoformat(),
                tracking_number="TRK987654321",
            )
        )

        # Older order (delivered)
        orders.append(
            CustomerOrder(
                order_id=f"ORD-{uuid4().hex[:8].upper()}",
                customer_id=customer_id,
                status="delivered",
                total_amount=49.98,
                items=[
                    {"name": "Coffee Mug", "quantity": 2, "price": 19.99},
                    {"name": "Standard Shipping", "quantity": 1, "price": 9.99},
                ],
                order_date=(datetime.now() - timedelta(days=45)).isoformat(),
                estimated_delivery=(datetime.now() - timedelta(days=42)).isoformat(),
                tracking_number="TRK555666777",
            )
        )

        self.orders[email] = orders

    def _create_sample_support_history(self, customer_id: str):
        """Create sample support history for a customer."""
        support_interactions = []

        # Resolved complaint
        support_interactions.append(
            CustomerSupport(
                interaction_id=f"SUP-{uuid4().hex[:8].upper()}",
                customer_id=customer_id,
                type="complaint",
                status="resolved",
                priority="medium",
                subject="Delayed delivery",
                description="My order was supposed to arrive yesterday but still hasn't arrived.",
                created_date=(datetime.now() - timedelta(days=30)).isoformat(),
                resolved_date=(datetime.now() - timedelta(days=28)).isoformat(),
                agent_id="AGT001",
            )
        )

        # Recent inquiry
        support_interactions.append(
            CustomerSupport(
                interaction_id=f"SUP-{uuid4().hex[:8].upper()}",
                customer_id=customer_id,
                type="inquiry",
                status="resolved",
                priority="low",
                subject="Return policy question",
                description="What's your return policy for electronics?",
                created_date=(datetime.now() - timedelta(days=7)).isoformat(),
                resolved_date=(datetime.now() - timedelta(days=6)).isoformat(),
                agent_id="AGT002",
            )
        )

        self.support_history[customer_id] = support_interactions

    async def get_customer_by_email(self, email: str) -> Optional[CustomerProfile]:
        """Get customer profile by email."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        customer = self.customers.get(email)
        if customer:
            self.logger.info(f"Retrieved customer profile for {email}")
        else:
            self.logger.warning(f"Customer not found: {email}")

        return customer

    async def get_customer_orders(self, email: str, limit: int = 10) -> List[CustomerOrder]:
        """Get customer order history."""
        # Simulate API delay
        await asyncio.sleep(0.2)

        orders = self.orders.get(email, [])
        limited_orders = orders[:limit]

        self.logger.info(f"Retrieved {len(limited_orders)} orders for {email}")
        return limited_orders

    async def get_customer_support_history(self, customer_id: str, limit: int = 5) -> List[CustomerSupport]:
        """Get customer support interaction history."""
        # Simulate API delay
        await asyncio.sleep(0.15)

        history = self.support_history.get(customer_id, [])
        limited_history = history[:limit]

        self.logger.info(f"Retrieved {len(limited_history)} support interactions for customer {customer_id}")
        return limited_history

    async def update_customer_tier(self, customer_id: str, new_tier: str) -> bool:
        """Update customer tier (for loyalty program)."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        # Find customer by ID
        for customer in self.customers.values():
            if customer.customer_id == customer_id:
                old_tier = customer.tier
                customer.tier = new_tier
                self.logger.info(f"Updated customer {customer_id} tier from {old_tier} to {new_tier}")
                return True

        self.logger.warning(f"Customer not found for tier update: {customer_id}")
        return False

    async def add_customer_note(self, customer_id: str, note: str, agent_id: str = "SYSTEM") -> bool:
        """Add a note to customer's support history."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        note_interaction = CustomerSupport(
            interaction_id=f"NOTE-{uuid4().hex[:8].upper()}",
            customer_id=customer_id,
            type="note",
            status="resolved",
            priority="low",
            subject="Agent Note",
            description=note,
            created_date=datetime.now().isoformat(),
            resolved_date=datetime.now().isoformat(),
            agent_id=agent_id,
        )

        if customer_id not in self.support_history:
            self.support_history[customer_id] = []

        self.support_history[customer_id].append(note_interaction)

        self.logger.info(f"Added note for customer {customer_id}")
        return True


# Global instance
mock_customer_api = MockCustomerAPI()

# FastAPI app for HTTP endpoints
app = FastAPI(title="Mock Customer API", version="1.0.0")


@app.get("/customers/{email}", response_model=CustomerProfile)
async def get_customer(email: str):
    """Get customer profile by email."""
    customer = await mock_customer_api.get_customer_by_email(email)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@app.get("/customers/{email}/orders", response_model=List[CustomerOrder])
async def get_customer_orders(email: str, limit: int = 10):
    """Get customer order history."""
    # First check if customer exists
    customer = await mock_customer_api.get_customer_by_email(email)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    orders = await mock_customer_api.get_customer_orders(email, limit)
    return orders


@app.get("/customers/{customer_id}/support-history", response_model=List[CustomerSupport])
async def get_support_history(customer_id: str, limit: int = 5):
    """Get customer support history."""
    history = await mock_customer_api.get_customer_support_history(customer_id, limit)
    return history


@app.put("/customers/{customer_id}/tier")
async def update_customer_tier(customer_id: str, tier_data: dict):
    """Update customer tier."""
    new_tier = tier_data.get("tier")
    if not new_tier:
        raise HTTPException(status_code=400, detail="Tier is required")

    success = await mock_customer_api.update_customer_tier(customer_id, new_tier)
    if not success:
        raise HTTPException(status_code=404, detail="Customer not found")

    return {"message": "Customer tier updated successfully"}


@app.post("/customers/{customer_id}/notes")
async def add_customer_note(customer_id: str, note_data: dict):
    """Add a note to customer's record."""
    note = note_data.get("note")
    agent_id = note_data.get("agent_id", "SYSTEM")

    if not note:
        raise HTTPException(status_code=400, detail="Note is required")

    success = await mock_customer_api.add_customer_note(customer_id, note, agent_id)
    return {"message": "Note added successfully"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Mock Customer API",
        "customers_count": len(mock_customer_api.customers),
        "timestamp": datetime.now().isoformat(),
    }


# Utility functions for direct access (non-HTTP)
async def get_customer_api() -> MockCustomerAPI:
    """Get the mock customer API instance."""
    return mock_customer_api
