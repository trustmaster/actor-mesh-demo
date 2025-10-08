"""
Mock Delivery Tracking API service for the Actor Mesh Demo.

This module provides a mock delivery tracking service API that simulates
package tracking, delivery status updates, and shipping carrier integration.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class TrackingEvent(BaseModel):
    """Tracking event data structure."""

    event_id: str
    tracking_number: str
    status: str  # picked_up, in_transit, out_for_delivery, delivered, exception
    location: str
    description: str
    timestamp: str
    facility: Optional[str] = None


class DeliveryAddress(BaseModel):
    """Delivery address data structure."""

    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"


class PackageInfo(BaseModel):
    """Package information data structure."""

    tracking_number: str
    carrier: str  # fedex, ups, usps, dhl
    service_type: str  # standard, express, overnight
    weight: Optional[float] = None
    dimensions: Optional[Dict[str, float]] = None
    declared_value: Optional[float] = None


class DeliveryDetails(BaseModel):
    """Complete delivery tracking details."""

    tracking_number: str
    order_id: Optional[str] = None
    carrier: str
    service_type: str
    current_status: str

    origin_address: DeliveryAddress
    destination_address: DeliveryAddress

    estimated_delivery: Optional[str] = None
    actual_delivery: Optional[str] = None

    package_info: PackageInfo
    tracking_events: List[TrackingEvent] = []

    delivery_instructions: Optional[str] = None
    signature_required: bool = False
    delivered_to: Optional[str] = None

    created_at: str
    last_updated: str


class DeliveryException(BaseModel):
    """Delivery exception/issue data structure."""

    exception_id: str
    tracking_number: str
    exception_type: str  # delay, damaged, lost, delivery_failed, address_issue
    description: str
    resolution_status: str  # reported, investigating, resolved
    reported_at: str
    resolved_at: Optional[str] = None


class MockTrackingAPI:
    """Mock delivery tracking API implementation."""

    def __init__(self):
        """Initialize mock data."""
        self.logger = logging.getLogger("mock_tracking_api")

        # Mock tracking database
        self.deliveries: Dict[str, DeliveryDetails] = {}
        self.exceptions: Dict[str, DeliveryException] = {}

        # Carrier service types
        self.carrier_services = {
            "fedex": ["Ground", "Express", "Overnight"],
            "ups": ["Ground", "Next Day Air", "2nd Day Air"],
            "usps": ["Priority", "Express", "First-Class"],
            "dhl": ["Express", "Ground", "International"],
        }

        # Status progression
        self.status_flow = ["label_created", "picked_up", "in_transit", "out_for_delivery", "delivered"]

        # Initialize with sample data
        self._initialize_mock_data()

    def _initialize_mock_data(self):
        """Create sample delivery data."""
        # Sample deliveries for different scenarios
        sample_deliveries = [
            {
                "tracking_number": "TRK123456789",
                "order_id": "ORD-12345678",
                "carrier": "fedex",
                "service_type": "Ground",
                "status": "delivered",
                "days_ago": 1,
                "destination": {"street": "123 Main St", "city": "Anytown", "state": "CA", "zip_code": "12345"},
            },
            {
                "tracking_number": "TRK987654321",
                "order_id": "ORD-87654321",
                "carrier": "ups",
                "service_type": "Next Day Air",
                "status": "out_for_delivery",
                "days_ago": 0,
                "destination": {"street": "456 Oak Ave", "city": "Springfield", "state": "NY", "zip_code": "67890"},
            },
            {
                "tracking_number": "TRK555666777",
                "order_id": "ORD-55566677",
                "carrier": "usps",
                "service_type": "Priority",
                "status": "in_transit",
                "days_ago": 2,
                "destination": {"street": "789 Pine St", "city": "Portland", "state": "OR", "zip_code": "97201"},
            },
            {
                "tracking_number": "TRK111222333",
                "order_id": "ORD-11122233",
                "carrier": "fedex",
                "service_type": "Express",
                "status": "exception",
                "days_ago": 1,
                "destination": {"street": "321 Elm St", "city": "Boston", "state": "MA", "zip_code": "02101"},
            },
        ]

        for delivery_data in sample_deliveries:
            self._create_sample_delivery(delivery_data)

    def _create_sample_delivery(self, delivery_data: Dict[str, Any]):
        """Create a sample delivery from template data."""
        tracking_number = delivery_data["tracking_number"]

        # Create addresses
        origin = DeliveryAddress(street="1000 Warehouse Blvd", city="Distribution Center", state="TX", zip_code="75001")

        destination = DeliveryAddress(**delivery_data["destination"])

        # Create package info
        package_info = PackageInfo(
            tracking_number=tracking_number,
            carrier=delivery_data["carrier"],
            service_type=delivery_data["service_type"],
            weight=2.5,
            dimensions={"length": 12.0, "width": 8.0, "height": 4.0},
            declared_value=150.00,
        )

        # Calculate dates
        ship_date = datetime.now() - timedelta(days=delivery_data["days_ago"] + 1)
        current_status = delivery_data["status"]

        estimated_delivery = ship_date + timedelta(days=3)
        actual_delivery = None

        if current_status == "delivered":
            actual_delivery = ship_date + timedelta(days=2)

        # Create tracking events
        events = self._generate_tracking_events(tracking_number, current_status, ship_date, origin, destination)

        # Create delivery details
        delivery = DeliveryDetails(
            tracking_number=tracking_number,
            order_id=delivery_data.get("order_id"),
            carrier=delivery_data["carrier"],
            service_type=delivery_data["service_type"],
            current_status=current_status,
            origin_address=origin,
            destination_address=destination,
            estimated_delivery=estimated_delivery.isoformat(),
            actual_delivery=actual_delivery.isoformat() if actual_delivery else None,
            package_info=package_info,
            tracking_events=events,
            signature_required=delivery_data["service_type"] in ["Express", "Overnight", "Next Day Air"],
            created_at=ship_date.isoformat(),
            last_updated=datetime.now().isoformat(),
        )

        self.deliveries[tracking_number] = delivery

        # Create exception if status is "exception"
        if current_status == "exception":
            self._create_sample_exception(tracking_number)

    def _generate_tracking_events(
        self,
        tracking_number: str,
        current_status: str,
        ship_date: datetime,
        origin: DeliveryAddress,
        destination: DeliveryAddress,
    ) -> List[TrackingEvent]:
        """Generate tracking events based on current status."""
        events = []
        current_time = ship_date

        # Label created
        events.append(
            TrackingEvent(
                event_id=f"EVT-{uuid4().hex[:8].upper()}",
                tracking_number=tracking_number,
                status="label_created",
                location=f"{origin.city}, {origin.state}",
                description="Shipping label created",
                timestamp=current_time.isoformat(),
                facility="Origin Facility",
            )
        )

        if current_status in ["picked_up", "in_transit", "out_for_delivery", "delivered", "exception"]:
            current_time += timedelta(hours=2)
            events.append(
                TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="picked_up",
                    location=f"{origin.city}, {origin.state}",
                    description="Package picked up by carrier",
                    timestamp=current_time.isoformat(),
                    facility="Origin Facility",
                )
            )

        if current_status in ["in_transit", "out_for_delivery", "delivered", "exception"]:
            current_time += timedelta(hours=6)
            events.append(
                TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="in_transit",
                    location="Distribution Hub, TX",
                    description="Package in transit to destination facility",
                    timestamp=current_time.isoformat(),
                    facility="Houston Distribution Center",
                )
            )

            current_time += timedelta(hours=18)
            events.append(
                TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="in_transit",
                    location=f"{destination.city}, {destination.state}",
                    description="Arrived at destination facility",
                    timestamp=current_time.isoformat(),
                    facility=f"{destination.city} Distribution Center",
                )
            )

        if current_status in ["out_for_delivery", "delivered"]:
            current_time += timedelta(hours=12)
            events.append(
                TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="out_for_delivery",
                    location=f"{destination.city}, {destination.state}",
                    description="Out for delivery",
                    timestamp=current_time.isoformat(),
                    facility=f"{destination.city} Delivery Station",
                )
            )

        if current_status == "delivered":
            current_time += timedelta(hours=4)
            events.append(
                TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="delivered",
                    location=f"{destination.street}, {destination.city}, {destination.state}",
                    description="Package delivered",
                    timestamp=current_time.isoformat(),
                )
            )

        if current_status == "exception":
            current_time += timedelta(hours=8)
            events.append(
                TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="exception",
                    location=f"{destination.city}, {destination.state}",
                    description="Delivery exception - Address correction needed",
                    timestamp=current_time.isoformat(),
                    facility=f"{destination.city} Delivery Station",
                )
            )

        return events

    def _create_sample_exception(self, tracking_number: str):
        """Create a sample delivery exception."""
        exception = DeliveryException(
            exception_id=f"EXC-{uuid4().hex[:8].upper()}",
            tracking_number=tracking_number,
            exception_type="address_issue",
            description="Incorrect or incomplete delivery address",
            resolution_status="reported",
            reported_at=datetime.now().isoformat(),
        )

        self.exceptions[tracking_number] = exception

    async def get_tracking_info(self, tracking_number: str) -> Optional[DeliveryDetails]:
        """Get tracking information by tracking number."""
        # Simulate API delay
        await asyncio.sleep(0.15)

        delivery = self.deliveries.get(tracking_number)
        if delivery:
            self.logger.info(f"Retrieved tracking info for {tracking_number}")
        else:
            self.logger.warning(f"Tracking number not found: {tracking_number}")

        return delivery

    async def get_delivery_status(self, tracking_number: str) -> Optional[str]:
        """Get current delivery status."""
        # Simulate API delay
        await asyncio.sleep(0.05)

        delivery = self.deliveries.get(tracking_number)
        return delivery.current_status if delivery else None

    async def update_delivery_address(
        self, tracking_number: str, new_address: DeliveryAddress, updated_by: str = "SYSTEM"
    ) -> bool:
        """Update delivery address (address correction)."""
        # Simulate API delay
        await asyncio.sleep(0.2)

        delivery = self.deliveries.get(tracking_number)
        if not delivery:
            return False

        # Can only update address if not yet delivered
        if delivery.current_status in ["delivered"]:
            self.logger.warning(f"Cannot update address for delivered package: {tracking_number}")
            return False

        old_address = delivery.destination_address
        delivery.destination_address = new_address
        delivery.last_updated = datetime.now().isoformat()

        # Add tracking event
        event = TrackingEvent(
            event_id=f"EVT-{uuid4().hex[:8].upper()}",
            tracking_number=tracking_number,
            status="address_updated",
            location=f"{new_address.city}, {new_address.state}",
            description=f"Delivery address updated by {updated_by}",
            timestamp=datetime.now().isoformat(),
        )

        delivery.tracking_events.append(event)

        # Resolve any address-related exceptions
        if tracking_number in self.exceptions:
            exception = self.exceptions[tracking_number]
            if exception.exception_type == "address_issue":
                exception.resolution_status = "resolved"
                exception.resolved_at = datetime.now().isoformat()

        self.logger.info(f"Updated delivery address for {tracking_number}")
        return True

    async def expedite_delivery(self, tracking_number: str, new_service: str, expedited_by: str = "SYSTEM") -> bool:
        """Expedite a delivery by upgrading service type."""
        # Simulate API delay
        await asyncio.sleep(0.2)

        delivery = self.deliveries.get(tracking_number)
        if not delivery:
            return False

        # Can only expedite if not yet out for delivery
        if delivery.current_status in ["out_for_delivery", "delivered"]:
            self.logger.warning(f"Cannot expedite package already out for delivery: {tracking_number}")
            return False

        old_service = delivery.service_type
        delivery.service_type = new_service
        delivery.package_info.service_type = new_service

        # Update estimated delivery (make it sooner)
        if delivery.estimated_delivery:
            current_estimate = datetime.fromisoformat(delivery.estimated_delivery)
            new_estimate = current_estimate - timedelta(days=1)
            delivery.estimated_delivery = new_estimate.isoformat()

        delivery.last_updated = datetime.now().isoformat()

        # Add tracking event
        event = TrackingEvent(
            event_id=f"EVT-{uuid4().hex[:8].upper()}",
            tracking_number=tracking_number,
            status="service_upgraded",
            location="Processing Facility",
            description=f"Service upgraded from {old_service} to {new_service} by {expedited_by}",
            timestamp=datetime.now().isoformat(),
        )

        delivery.tracking_events.append(event)

        self.logger.info(f"Expedited delivery {tracking_number} from {old_service} to {new_service}")
        return True

    async def report_delivery_issue(
        self, tracking_number: str, issue_type: str, description: str, reported_by: str = "CUSTOMER"
    ) -> str:
        """Report a delivery issue."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        # Create exception record
        exception_id = f"EXC-{uuid4().hex[:8].upper()}"
        exception = DeliveryException(
            exception_id=exception_id,
            tracking_number=tracking_number,
            exception_type=issue_type,
            description=description,
            resolution_status="reported",
            reported_at=datetime.now().isoformat(),
        )

        self.exceptions[tracking_number] = exception

        # Update delivery status if needed
        if tracking_number in self.deliveries:
            delivery = self.deliveries[tracking_number]
            if delivery.current_status != "exception":
                delivery.current_status = "exception"
                delivery.last_updated = datetime.now().isoformat()

                # Add tracking event
                event = TrackingEvent(
                    event_id=f"EVT-{uuid4().hex[:8].upper()}",
                    tracking_number=tracking_number,
                    status="exception",
                    location="Customer Service",
                    description=f"Delivery issue reported: {description}",
                    timestamp=datetime.now().isoformat(),
                )

                delivery.tracking_events.append(event)

        self.logger.info(f"Reported delivery issue {exception_id} for {tracking_number}")
        return exception_id

    async def get_delivery_exceptions(self, tracking_number: str) -> List[DeliveryException]:
        """Get delivery exceptions for a tracking number."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        exceptions = []
        if tracking_number in self.exceptions:
            exceptions.append(self.exceptions[tracking_number])

        return exceptions


# Global instance
mock_tracking_api = MockTrackingAPI()

# FastAPI app for HTTP endpoints
app = FastAPI(title="Mock Delivery Tracking API", version="1.0.0")


@app.get("/tracking/{tracking_number}", response_model=DeliveryDetails)
async def get_tracking(tracking_number: str):
    """Get tracking information."""
    delivery = await mock_tracking_api.get_tracking_info(tracking_number)
    if not delivery:
        raise HTTPException(status_code=404, detail="Tracking number not found")
    return delivery


@app.get("/tracking/{tracking_number}/status")
async def get_status(tracking_number: str):
    """Get current delivery status."""
    status = await mock_tracking_api.get_delivery_status(tracking_number)
    if not status:
        raise HTTPException(status_code=404, detail="Tracking number not found")
    return {"tracking_number": tracking_number, "status": status}


@app.put("/tracking/{tracking_number}/address")
async def update_address(tracking_number: str, address_data: dict):
    """Update delivery address."""
    try:
        new_address = DeliveryAddress(**address_data["address"])
        updated_by = address_data.get("updated_by", "API")

        success = await mock_tracking_api.update_delivery_address(tracking_number, new_address, updated_by)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot update delivery address")

        return {"message": "Delivery address updated successfully"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid address data: {str(e)}")


@app.post("/tracking/{tracking_number}/expedite")
async def expedite_delivery(tracking_number: str, expedite_data: dict):
    """Expedite delivery."""
    new_service = expedite_data.get("service_type", "Express")
    expedited_by = expedite_data.get("expedited_by", "API")

    success = await mock_tracking_api.expedite_delivery(tracking_number, new_service, expedited_by)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot expedite delivery")

    return {"message": "Delivery expedited successfully"}


@app.post("/tracking/{tracking_number}/issues")
async def report_issue(tracking_number: str, issue_data: dict):
    """Report a delivery issue."""
    issue_type = issue_data.get("issue_type", "other")
    description = issue_data.get("description", "No description provided")
    reported_by = issue_data.get("reported_by", "API")

    exception_id = await mock_tracking_api.report_delivery_issue(tracking_number, issue_type, description, reported_by)

    return {"message": "Issue reported successfully", "exception_id": exception_id}


@app.get("/tracking/{tracking_number}/exceptions", response_model=List[DeliveryException])
async def get_exceptions(tracking_number: str):
    """Get delivery exceptions."""
    exceptions = await mock_tracking_api.get_delivery_exceptions(tracking_number)
    return exceptions


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Mock Delivery Tracking API",
        "deliveries_count": len(mock_tracking_api.deliveries),
        "timestamp": datetime.now().isoformat(),
    }


# Utility functions for direct access (non-HTTP)
async def get_tracking_api() -> MockTrackingAPI:
    """Get the mock tracking API instance."""
    return mock_tracking_api
