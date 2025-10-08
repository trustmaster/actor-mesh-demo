"""
Mock Orders API service for the Actor Mesh Demo.

This module provides a mock orders service API that simulates
order management, status updates, and order modification operations.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class OrderItem(BaseModel):
    """Order item data structure."""

    item_id: str
    product_id: str
    name: str
    quantity: int
    unit_price: float
    total_price: float
    sku: Optional[str] = None


class ShippingAddress(BaseModel):
    """Shipping address data structure."""

    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"


class OrderDetails(BaseModel):
    """Complete order details data structure."""

    order_id: str
    customer_id: str
    customer_email: str
    status: str  # pending, confirmed, processing, shipped, delivered, cancelled, returned
    subtotal: float
    tax_amount: float
    shipping_cost: float
    total_amount: float
    currency: str = "USD"

    items: List[OrderItem]
    shipping_address: ShippingAddress
    billing_address: Optional[ShippingAddress] = None

    order_date: str
    estimated_delivery: Optional[str] = None
    actual_delivery: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None

    payment_method: str = "credit_card"
    payment_status: str = "paid"  # pending, paid, failed, refunded

    notes: List[str] = []
    last_updated: str


class OrderStatusUpdate(BaseModel):
    """Order status update data structure."""

    order_id: str
    old_status: str
    new_status: str
    updated_by: str
    timestamp: str
    reason: Optional[str] = None


class MockOrdersAPI:
    """Mock orders API implementation."""

    def __init__(self):
        """Initialize mock data."""
        self.logger = logging.getLogger("mock_orders_api")

        # Mock orders database
        self.orders: Dict[str, OrderDetails] = {}
        self.status_history: Dict[str, List[OrderStatusUpdate]] = {}

        # Valid status transitions
        self.valid_transitions = {
            "pending": ["confirmed", "cancelled"],
            "confirmed": ["processing", "cancelled"],
            "processing": ["shipped", "cancelled"],
            "shipped": ["delivered", "returned"],
            "delivered": ["returned"],
            "cancelled": [],
            "returned": [],
        }

        # Initialize with sample data
        self._initialize_mock_data()

    def _initialize_mock_data(self):
        """Create sample order data."""
        # Sample orders for different scenarios
        sample_orders = [
            {
                "customer_email": "john.doe@example.com",
                "status": "delivered",
                "days_ago": 15,
                "items": [
                    {"name": "Wireless Headphones", "quantity": 1, "unit_price": 99.99},
                    {"name": "Phone Case", "quantity": 1, "unit_price": 19.99},
                ],
                "shipping_cost": 9.99,
                "tracking": "TRK123456789",
                "carrier": "FedEx",
            },
            {
                "customer_email": "john.doe@example.com",
                "status": "shipped",
                "days_ago": 3,
                "items": [
                    {"name": "Laptop Stand", "quantity": 1, "unit_price": 79.99},
                    {"name": "USB Hub", "quantity": 2, "unit_price": 44.99},
                ],
                "shipping_cost": 15.99,
                "tracking": "TRK987654321",
                "carrier": "UPS",
            },
            {
                "customer_email": "jane.smith@example.com",
                "status": "processing",
                "days_ago": 1,
                "items": [
                    {"name": "Gaming Mouse", "quantity": 1, "unit_price": 59.99},
                    {"name": "Mouse Pad", "quantity": 1, "unit_price": 24.99},
                ],
                "shipping_cost": 7.99,
            },
            {
                "customer_email": "bob.wilson@example.com",
                "status": "pending",
                "days_ago": 0,
                "items": [{"name": "Coffee Maker", "quantity": 1, "unit_price": 149.99}],
                "shipping_cost": 12.99,
            },
        ]

        for order_data in sample_orders:
            self._create_sample_order(order_data)

    def _create_sample_order(self, order_data: Dict[str, Any]):
        """Create a sample order from template data."""
        order_id = f"ORD-{uuid4().hex[:8].upper()}"
        customer_id = str(uuid4())

        # Calculate order totals
        items = []
        subtotal = 0.0

        for item_data in order_data["items"]:
            item = OrderItem(
                item_id=f"ITM-{uuid4().hex[:6].upper()}",
                product_id=f"PRD-{uuid4().hex[:6].upper()}",
                name=item_data["name"],
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                total_price=item_data["quantity"] * item_data["unit_price"],
                sku=f"SKU-{uuid4().hex[:8].upper()}",
            )
            items.append(item)
            subtotal += item.total_price

        shipping_cost = order_data.get("shipping_cost", 0.0)
        tax_amount = round(subtotal * 0.0875, 2)  # 8.75% tax
        total_amount = subtotal + tax_amount + shipping_cost

        # Create shipping address
        shipping_address = ShippingAddress(
            street="123 Main St", city="Anytown", state="CA", zip_code="12345", country="US"
        )

        # Calculate dates
        order_date = datetime.now() - timedelta(days=order_data["days_ago"])
        estimated_delivery = None
        actual_delivery = None

        if order_data["status"] in ["shipped", "delivered"]:
            estimated_delivery = order_date + timedelta(days=5)

        if order_data["status"] == "delivered":
            actual_delivery = order_date + timedelta(days=4)

        # Create order
        order = OrderDetails(
            order_id=order_id,
            customer_id=customer_id,
            customer_email=order_data["customer_email"],
            status=order_data["status"],
            subtotal=subtotal,
            tax_amount=tax_amount,
            shipping_cost=shipping_cost,
            total_amount=total_amount,
            items=items,
            shipping_address=shipping_address,
            billing_address=shipping_address,
            order_date=order_date.isoformat(),
            estimated_delivery=estimated_delivery.isoformat() if estimated_delivery else None,
            actual_delivery=actual_delivery.isoformat() if actual_delivery else None,
            tracking_number=order_data.get("tracking"),
            carrier=order_data.get("carrier"),
            last_updated=datetime.now().isoformat(),
        )

        self.orders[order_id] = order

        # Create status history
        self.status_history[order_id] = [
            OrderStatusUpdate(
                order_id=order_id,
                old_status="created",
                new_status=order_data["status"],
                updated_by="SYSTEM",
                timestamp=order_date.isoformat(),
                reason="Order created",
            )
        ]

    async def get_order_by_id(self, order_id: str) -> Optional[OrderDetails]:
        """Get order details by order ID."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        order = self.orders.get(order_id)
        if order:
            self.logger.info(f"Retrieved order {order_id}")
        else:
            self.logger.warning(f"Order not found: {order_id}")

        return order

    async def get_orders_by_customer(self, customer_email: str, limit: int = 10) -> List[OrderDetails]:
        """Get orders for a customer."""
        # Simulate API delay
        await asyncio.sleep(0.2)

        customer_orders = []
        for order in self.orders.values():
            if order.customer_email == customer_email:
                customer_orders.append(order)

        # Sort by order date (newest first)
        customer_orders.sort(key=lambda x: x.order_date, reverse=True)
        limited_orders = customer_orders[:limit]

        self.logger.info(f"Retrieved {len(limited_orders)} orders for {customer_email}")
        return limited_orders

    async def update_order_status(
        self, order_id: str, new_status: str, updated_by: str = "SYSTEM", reason: str = None
    ) -> bool:
        """Update order status with validation."""
        # Simulate API delay
        await asyncio.sleep(0.15)

        order = self.orders.get(order_id)
        if not order:
            self.logger.warning(f"Order not found for status update: {order_id}")
            return False

        old_status = order.status

        # Validate status transition
        if new_status not in self.valid_transitions.get(old_status, []):
            self.logger.warning(f"Invalid status transition from {old_status} to {new_status} for order {order_id}")
            return False

        # Update order
        order.status = new_status
        order.last_updated = datetime.now().isoformat()

        # Add tracking info for shipped orders
        if new_status == "shipped" and not order.tracking_number:
            order.tracking_number = f"TRK{uuid4().hex[:9].upper()}"
            order.carrier = "FedEx"

        # Set delivery date for delivered orders
        if new_status == "delivered" and not order.actual_delivery:
            order.actual_delivery = datetime.now().isoformat()

        # Record status change
        status_update = OrderStatusUpdate(
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            updated_by=updated_by,
            timestamp=datetime.now().isoformat(),
            reason=reason,
        )

        if order_id not in self.status_history:
            self.status_history[order_id] = []

        self.status_history[order_id].append(status_update)

        self.logger.info(f"Updated order {order_id} status from {old_status} to {new_status}")
        return True

    async def expedite_order(self, order_id: str, expedited_by: str = "SYSTEM") -> bool:
        """Expedite an order (upgrade shipping)."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        order = self.orders.get(order_id)
        if not order:
            return False

        # Can only expedite orders that are confirmed or processing
        if order.status not in ["confirmed", "processing"]:
            self.logger.warning(f"Cannot expedite order {order_id} with status {order.status}")
            return False

        # Update estimated delivery (make it sooner)
        if order.estimated_delivery:
            current_estimate = datetime.fromisoformat(order.estimated_delivery)
            new_estimate = current_estimate - timedelta(days=2)
            order.estimated_delivery = new_estimate.isoformat()

        # Add note
        order.notes.append(f"Order expedited by {expedited_by} at {datetime.now().isoformat()}")
        order.last_updated = datetime.now().isoformat()

        self.logger.info(f"Expedited order {order_id}")
        return True

    async def cancel_order(self, order_id: str, cancelled_by: str = "SYSTEM", reason: str = None) -> bool:
        """Cancel an order."""
        return await self.update_order_status(order_id, "cancelled", cancelled_by, reason)

    async def add_order_note(self, order_id: str, note: str, added_by: str = "SYSTEM") -> bool:
        """Add a note to an order."""
        # Simulate API delay
        await asyncio.sleep(0.05)

        order = self.orders.get(order_id)
        if not order:
            return False

        timestamp = datetime.now().isoformat()
        formatted_note = f"[{timestamp}] {added_by}: {note}"

        order.notes.append(formatted_note)
        order.last_updated = timestamp

        self.logger.info(f"Added note to order {order_id}")
        return True

    async def get_order_status_history(self, order_id: str) -> List[OrderStatusUpdate]:
        """Get status change history for an order."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        history = self.status_history.get(order_id, [])
        self.logger.info(f"Retrieved {len(history)} status updates for order {order_id}")
        return history

    async def process_refund(self, order_id: str, amount: float, reason: str, processed_by: str = "SYSTEM") -> bool:
        """Process a refund for an order."""
        # Simulate API delay
        await asyncio.sleep(0.3)

        order = self.orders.get(order_id)
        if not order:
            return False

        # Can only refund delivered or cancelled orders
        if order.status not in ["delivered", "cancelled", "returned"]:
            self.logger.warning(f"Cannot refund order {order_id} with status {order.status}")
            return False

        # Update payment status
        order.payment_status = "refunded"

        # Add refund note
        refund_note = f"Refund processed: ${amount:.2f} - Reason: {reason} - Processed by: {processed_by}"
        order.notes.append(f"[{datetime.now().isoformat()}] {refund_note}")
        order.last_updated = datetime.now().isoformat()

        self.logger.info(f"Processed refund of ${amount:.2f} for order {order_id}")
        return True


# Global instance
mock_orders_api = MockOrdersAPI()

# FastAPI app for HTTP endpoints
app = FastAPI(title="Mock Orders API", version="1.0.0")


@app.get("/orders/{order_id}", response_model=OrderDetails)
async def get_order(order_id: str):
    """Get order details by ID."""
    order = await mock_orders_api.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/customers/{customer_email}/orders", response_model=List[OrderDetails])
async def get_customer_orders(customer_email: str, limit: int = 10):
    """Get orders for a customer."""
    orders = await mock_orders_api.get_orders_by_customer(customer_email, limit)
    return orders


@app.put("/orders/{order_id}/status")
async def update_order_status(order_id: str, status_data: dict):
    """Update order status."""
    new_status = status_data.get("status")
    updated_by = status_data.get("updated_by", "API")
    reason = status_data.get("reason")

    if not new_status:
        raise HTTPException(status_code=400, detail="Status is required")

    success = await mock_orders_api.update_order_status(order_id, new_status, updated_by, reason)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid status update")

    return {"message": "Order status updated successfully"}


@app.post("/orders/{order_id}/expedite")
async def expedite_order(order_id: str, expedite_data: dict = {}):
    """Expedite an order."""
    expedited_by = expedite_data.get("expedited_by", "API")

    success = await mock_orders_api.expedite_order(order_id, expedited_by)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot expedite order")

    return {"message": "Order expedited successfully"}


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, cancel_data: dict):
    """Cancel an order."""
    cancelled_by = cancel_data.get("cancelled_by", "API")
    reason = cancel_data.get("reason", "Customer request")

    success = await mock_orders_api.cancel_order(order_id, cancelled_by, reason)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel order")

    return {"message": "Order cancelled successfully"}


@app.post("/orders/{order_id}/notes")
async def add_order_note(order_id: str, note_data: dict):
    """Add a note to an order."""
    note = note_data.get("note")
    added_by = note_data.get("added_by", "API")

    if not note:
        raise HTTPException(status_code=400, detail="Note is required")

    success = await mock_orders_api.add_order_note(order_id, note, added_by)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")

    return {"message": "Note added successfully"}


@app.get("/orders/{order_id}/history", response_model=List[OrderStatusUpdate])
async def get_order_history(order_id: str):
    """Get order status history."""
    history = await mock_orders_api.get_order_status_history(order_id)
    return history


@app.post("/orders/{order_id}/refund")
async def process_refund(order_id: str, refund_data: dict):
    """Process a refund for an order."""
    amount = refund_data.get("amount")
    reason = refund_data.get("reason", "Customer request")
    processed_by = refund_data.get("processed_by", "API")

    if not amount:
        raise HTTPException(status_code=400, detail="Refund amount is required")

    try:
        amount = float(amount)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid refund amount")

    success = await mock_orders_api.process_refund(order_id, amount, reason, processed_by)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot process refund")

    return {"message": "Refund processed successfully"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Mock Orders API",
        "orders_count": len(mock_orders_api.orders),
        "timestamp": datetime.now().isoformat(),
    }


# Utility functions for direct access (non-HTTP)
async def get_orders_api() -> MockOrdersAPI:
    """Get the mock orders API instance."""
    return mock_orders_api
