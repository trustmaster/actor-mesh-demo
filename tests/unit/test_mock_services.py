"""
Unit tests for mock services.

Tests the mock API services including CustomerAPI, OrdersAPI, and TrackingAPI
to ensure they provide realistic test data and handle various scenarios correctly.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from mock_services.customer_api import (
    CustomerOrder,
    CustomerProfile,
    CustomerSupport,
    MockCustomerAPI,
    get_customer_api,
)
from mock_services.customer_api import (
    app as customer_app,
)


class TestCustomerProfile:
    """Test cases for CustomerProfile model."""

    def test_customer_profile_creation(self):
        """Test creating a customer profile."""
        profile = CustomerProfile(
            customer_id="CUST-12345",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            phone="+1-555-0123",
            tier="premium",
            registration_date="2023-01-15T10:30:00",
        )

        assert profile.customer_id == "CUST-12345"
        assert profile.email == "test@example.com"
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"
        assert profile.phone == "+1-555-0123"
        assert profile.tier == "premium"
        assert profile.account_status == "active"  # Default value

    def test_customer_profile_optional_fields(self):
        """Test customer profile with minimal required fields."""
        profile = CustomerProfile(
            customer_id="CUST-12345",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            registration_date="2023-01-15T10:30:00",
        )

        assert profile.phone is None
        assert profile.last_login is None
        assert profile.preferences == {}
        assert profile.address is None

    def test_customer_profile_with_preferences(self):
        """Test customer profile with preferences."""
        preferences = {
            "email_notifications": True,
            "sms_notifications": False,
            "newsletter": True,
        }

        profile = CustomerProfile(
            customer_id="CUST-12345",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            registration_date="2023-01-15T10:30:00",
            preferences=preferences,
        )

        assert profile.preferences == preferences


class TestCustomerOrder:
    """Test cases for CustomerOrder model."""

    def test_customer_order_creation(self):
        """Test creating a customer order."""
        items = [
            {"name": "Laptop", "quantity": 1, "price": 999.99},
            {"name": "Mouse", "quantity": 1, "price": 29.99},
        ]

        order = CustomerOrder(
            order_id="ORD-12345",
            customer_id="CUST-12345",
            status="shipped",
            total_amount=1029.98,
            items=items,
            order_date="2024-01-10T14:30:00",
            tracking_number="TRK123456789",
        )

        assert order.order_id == "ORD-12345"
        assert order.customer_id == "CUST-12345"
        assert order.status == "shipped"
        assert order.total_amount == 1029.98
        assert order.currency == "USD"  # Default value
        assert len(order.items) == 2
        assert order.tracking_number == "TRK123456789"

    def test_customer_order_minimal(self):
        """Test customer order with minimal required fields."""
        order = CustomerOrder(
            order_id="ORD-12345",
            customer_id="CUST-12345",
            status="pending",
            total_amount=100.0,
            items=[{"name": "Test Item", "quantity": 1, "price": 100.0}],
            order_date="2024-01-10T14:30:00",
        )

        assert order.estimated_delivery is None
        assert order.tracking_number is None
        assert order.currency == "USD"


class TestCustomerSupport:
    """Test cases for CustomerSupport model."""

    def test_customer_support_creation(self):
        """Test creating a customer support interaction."""
        support = CustomerSupport(
            interaction_id="SUP-12345",
            customer_id="CUST-12345",
            type="complaint",
            status="in_progress",
            priority="high",
            subject="Order delivery issue",
            description="My order hasn't arrived and it's past the estimated delivery date.",
            created_date="2024-01-15T09:00:00",
            agent_id="AGT001",
        )

        assert support.interaction_id == "SUP-12345"
        assert support.customer_id == "CUST-12345"
        assert support.type == "complaint"
        assert support.status == "in_progress"
        assert support.priority == "high"
        assert support.subject == "Order delivery issue"
        assert support.agent_id == "AGT001"

    def test_customer_support_optional_fields(self):
        """Test customer support with minimal fields."""
        support = CustomerSupport(
            interaction_id="SUP-12345",
            customer_id="CUST-12345",
            type="inquiry",
            status="open",
            priority="low",
            subject="General question",
            description="I have a question about your return policy.",
            created_date="2024-01-15T09:00:00",
        )

        assert support.resolved_date is None
        assert support.agent_id is None


class TestMockCustomerAPI:
    """Test cases for MockCustomerAPI implementation."""

    @pytest.fixture
    def api(self):
        """Create a fresh MockCustomerAPI instance for testing."""
        return MockCustomerAPI()

    def test_api_initialization(self, api):
        """Test API initialization and sample data creation."""
        assert len(api.customers) > 0
        assert len(api.orders) > 0
        assert len(api.support_history) > 0

        # Check that sample customers exist
        sample_emails = ["john.doe@example.com", "jane.smith@example.com", "bob.wilson@example.com"]
        for email in sample_emails:
            assert email in api.customers

    def test_sample_data_structure(self, api):
        """Test structure of sample data."""
        # Check customers have required fields
        for customer in api.customers.values():
            assert isinstance(customer, CustomerProfile)
            assert customer.customer_id
            assert customer.email
            assert customer.first_name
            assert customer.last_name
            assert customer.tier in ["standard", "premium", "vip"]

        # Check orders are properly structured
        for email, orders in api.orders.items():
            assert isinstance(orders, list)
            for order in orders:
                assert isinstance(order, CustomerOrder)
                assert order.order_id
                assert order.customer_id

    @pytest.mark.asyncio
    async def test_get_customer_by_email_success(self, api):
        """Test successful customer retrieval by email."""
        email = "john.doe@example.com"
        customer = await api.get_customer_by_email(email)

        assert customer is not None
        assert isinstance(customer, CustomerProfile)
        assert customer.email == email
        assert customer.first_name == "John"
        assert customer.last_name == "Doe"

    @pytest.mark.asyncio
    async def test_get_customer_by_email_not_found(self, api):
        """Test customer retrieval with non-existent email."""
        email = "nonexistent@example.com"
        customer = await api.get_customer_by_email(email)

        assert customer is None

    @pytest.mark.asyncio
    async def test_get_customer_orders_success(self, api):
        """Test successful order retrieval."""
        email = "john.doe@example.com"
        orders = await api.get_customer_orders(email)

        assert isinstance(orders, list)
        assert len(orders) > 0

        for order in orders:
            assert isinstance(order, CustomerOrder)
            assert order.order_id
            assert order.customer_id

    @pytest.mark.asyncio
    async def test_get_customer_orders_with_limit(self, api):
        """Test order retrieval with limit."""
        email = "john.doe@example.com"
        limit = 2
        orders = await api.get_customer_orders(email, limit=limit)

        assert len(orders) <= limit

    @pytest.mark.asyncio
    async def test_get_customer_orders_nonexistent(self, api):
        """Test order retrieval for non-existent customer."""
        email = "nonexistent@example.com"
        orders = await api.get_customer_orders(email)

        assert isinstance(orders, list)
        assert len(orders) == 0

    @pytest.mark.asyncio
    async def test_get_customer_support_history_success(self, api):
        """Test successful support history retrieval."""
        # Get a customer ID from sample data
        customer = list(api.customers.values())[0]
        customer_id = customer.customer_id

        history = await api.get_customer_support_history(customer_id)

        assert isinstance(history, list)
        # May be empty for some customers, but should be a list
        for interaction in history:
            assert isinstance(interaction, CustomerSupport)
            assert interaction.customer_id == customer_id

    @pytest.mark.asyncio
    async def test_get_customer_support_history_with_limit(self, api):
        """Test support history retrieval with limit."""
        customer = list(api.customers.values())[0]
        customer_id = customer.customer_id
        limit = 3

        history = await api.get_customer_support_history(customer_id, limit=limit)

        assert len(history) <= limit

    @pytest.mark.asyncio
    async def test_get_customer_support_history_nonexistent(self, api):
        """Test support history retrieval for non-existent customer."""
        customer_id = "NONEXISTENT-ID"
        history = await api.get_customer_support_history(customer_id)

        assert isinstance(history, list)
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_update_customer_tier_success(self, api):
        """Test successful customer tier update."""
        customer = list(api.customers.values())[0]
        customer_id = customer.customer_id
        original_tier = customer.tier
        new_tier = "vip" if original_tier != "vip" else "premium"

        success = await api.update_customer_tier(customer_id, new_tier)

        assert success is True
        assert customer.tier == new_tier

    @pytest.mark.asyncio
    async def test_update_customer_tier_not_found(self, api):
        """Test customer tier update for non-existent customer."""
        customer_id = "NONEXISTENT-ID"
        new_tier = "premium"

        success = await api.update_customer_tier(customer_id, new_tier)

        assert success is False

    @pytest.mark.asyncio
    async def test_add_customer_note_success(self, api):
        """Test successfully adding a customer note."""
        customer = list(api.customers.values())[0]
        customer_id = customer.customer_id
        note = "Customer called to inquire about shipping."
        agent_id = "AGT123"

        success = await api.add_customer_note(customer_id, note, agent_id)

        assert success is True

        # Verify note was added
        history = await api.get_customer_support_history(customer_id)
        note_found = False
        for interaction in history:
            if interaction.type == "note" and interaction.description == note:
                assert interaction.agent_id == agent_id
                note_found = True
                break

        assert note_found

    @pytest.mark.asyncio
    async def test_add_customer_note_new_customer(self, api):
        """Test adding a note for a customer with no existing history."""
        customer_id = "NEW-CUSTOMER-ID"
        note = "First interaction with new customer."

        success = await api.add_customer_note(customer_id, note)

        assert success is True
        assert customer_id in api.support_history
        assert len(api.support_history[customer_id]) == 1

    @pytest.mark.asyncio
    async def test_api_delays_simulation(self, api):
        """Test that API calls include simulated delays."""
        import time

        start_time = time.time()
        await api.get_customer_by_email("john.doe@example.com")
        elapsed_time = time.time() - start_time

        # Should have some delay (at least 0.1 seconds)
        assert elapsed_time >= 0.1


class TestCustomerAPIHTTPEndpoints:
    """Test cases for HTTP endpoints of the Customer API."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        return TestClient(customer_app)

    def test_get_customer_success(self, client):
        """Test GET /customers/{email} success."""
        email = "john.doe@example.com"
        response = client.get(f"/customers/{email}")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == email
        assert "customer_id" in data
        assert "first_name" in data

    def test_get_customer_not_found(self, client):
        """Test GET /customers/{email} with non-existent customer."""
        email = "nonexistent@example.com"
        response = client.get(f"/customers/{email}")

        assert response.status_code == 404
        assert "Customer not found" in response.json()["detail"]

    def test_get_customer_orders_success(self, client):
        """Test GET /customers/{email}/orders success."""
        email = "john.doe@example.com"
        response = client.get(f"/customers/{email}/orders")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            order = data[0]
            assert "order_id" in order
            assert "customer_id" in order
            assert "status" in order

    def test_get_customer_orders_with_limit(self, client):
        """Test GET /customers/{email}/orders with limit parameter."""
        email = "john.doe@example.com"
        limit = 2
        response = client.get(f"/customers/{email}/orders?limit={limit}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= limit

    def test_get_customer_orders_customer_not_found(self, client):
        """Test GET /customers/{email}/orders for non-existent customer."""
        email = "nonexistent@example.com"
        response = client.get(f"/customers/{email}/orders")

        assert response.status_code == 404

    def test_get_support_history_success(self, client):
        """Test GET /customers/{customer_id}/support-history success."""
        # First get a customer to get their ID
        email = "john.doe@example.com"
        customer_response = client.get(f"/customers/{email}")
        customer_id = customer_response.json()["customer_id"]

        response = client.get(f"/customers/{customer_id}/support-history")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        for interaction in data:
            assert "interaction_id" in interaction
            assert interaction["customer_id"] == customer_id

    def test_update_customer_tier_success(self, client):
        """Test PUT /customers/{customer_id}/tier success."""
        # First get a customer to get their ID
        email = "john.doe@example.com"
        customer_response = client.get(f"/customers/{email}")
        customer_id = customer_response.json()["customer_id"]

        response = client.put(f"/customers/{customer_id}/tier", json={"tier": "vip"})

        assert response.status_code == 200
        assert "updated successfully" in response.json()["message"]

    def test_update_customer_tier_missing_data(self, client):
        """Test PUT /customers/{customer_id}/tier with missing tier data."""
        customer_id = "CUST-12345"
        response = client.put(f"/customers/{customer_id}/tier", json={})

        assert response.status_code == 400
        assert "Tier is required" in response.json()["detail"]

    def test_update_customer_tier_not_found(self, client):
        """Test PUT /customers/{customer_id}/tier for non-existent customer."""
        customer_id = "NONEXISTENT-ID"
        response = client.put(f"/customers/{customer_id}/tier", json={"tier": "premium"})

        assert response.status_code == 404

    def test_add_customer_note_success(self, client):
        """Test POST /customers/{customer_id}/notes success."""
        # First get a customer to get their ID
        email = "john.doe@example.com"
        customer_response = client.get(f"/customers/{email}")
        customer_id = customer_response.json()["customer_id"]

        response = client.post(
            f"/customers/{customer_id}/notes",
            json={"note": "Customer called about delivery inquiry", "agent_id": "AGT123"},
        )

        assert response.status_code == 200
        assert "added successfully" in response.json()["message"]

    def test_add_customer_note_missing_data(self, client):
        """Test POST /customers/{customer_id}/notes with missing note data."""
        customer_id = "CUST-12345"
        response = client.post(f"/customers/{customer_id}/notes", json={"agent_id": "AGT123"})

        assert response.status_code == 400
        assert "Note is required" in response.json()["detail"]

    def test_health_check(self, client):
        """Test GET /health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Mock Customer API"
        assert "customers_count" in data
        assert "timestamp" in data


class TestCustomerAPIUtilities:
    """Test cases for utility functions."""

    @pytest.mark.asyncio
    async def test_get_customer_api_function(self):
        """Test get_customer_api utility function."""
        api = await get_customer_api()

        assert isinstance(api, MockCustomerAPI)
        assert len(api.customers) > 0


class TestCustomerAPIDataConsistency:
    """Test cases for data consistency and relationships."""

    @pytest.fixture
    def api(self):
        """Create a fresh MockCustomerAPI instance for testing."""
        return MockCustomerAPI()

    @pytest.mark.asyncio
    async def test_customer_order_relationship(self, api):
        """Test that customer orders reference valid customers."""
        for email, orders in api.orders.items():
            # Email should exist in customers
            assert email in api.customers
            customer = api.customers[email]

            for order in orders:
                # Order customer_id should match customer
                assert order.customer_id == customer.customer_id

    @pytest.mark.asyncio
    async def test_support_history_consistency(self, api):
        """Test that support history references valid customers."""
        for customer_id, interactions in api.support_history.items():
            for interaction in interactions:
                # Support interaction customer_id should match
                assert interaction.customer_id == customer_id

    @pytest.mark.asyncio
    async def test_order_data_validity(self, api):
        """Test that order data is valid and consistent."""
        for orders in api.orders.values():
            for order in orders:
                # Order total should be reasonable
                assert order.total_amount > 0
                assert order.total_amount < 10000  # Reasonable upper bound

                # Items should exist and have valid data
                assert len(order.items) > 0
                for item in order.items:
                    assert "name" in item
                    assert "quantity" in item
                    assert "price" in item
                    assert item["quantity"] > 0
                    assert item["price"] >= 0

                # Status should be valid
                valid_statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
                assert order.status in valid_statuses

    @pytest.mark.asyncio
    async def test_customer_tier_validity(self, api):
        """Test that customer tiers are valid."""
        valid_tiers = ["standard", "premium", "vip"]

        for customer in api.customers.values():
            assert customer.tier in valid_tiers
            assert customer.account_status in ["active", "suspended", "premium"]

    @pytest.mark.asyncio
    async def test_date_formats(self, api):
        """Test that dates are in proper ISO format."""
        for customer in api.customers.values():
            # Should be able to parse registration date
            datetime.fromisoformat(customer.registration_date.replace("Z", "+00:00"))

            if customer.last_login:
                datetime.fromisoformat(customer.last_login.replace("Z", "+00:00"))

        for orders in api.orders.values():
            for order in orders:
                # Should be able to parse order date
                datetime.fromisoformat(order.order_date.replace("Z", "+00:00"))

                if order.estimated_delivery:
                    datetime.fromisoformat(order.estimated_delivery.replace("Z", "+00:00"))


class TestCustomerAPIPerformance:
    """Test cases for performance characteristics."""

    @pytest.fixture
    def api(self):
        """Create a MockCustomerAPI instance for testing."""
        return MockCustomerAPI()

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, api):
        """Test handling multiple concurrent requests."""
        import asyncio

        emails = list(api.customers.keys())[:3]

        # Create concurrent tasks
        tasks = [api.get_customer_by_email(email) for email in emails]

        # Execute concurrently
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == len(emails)
        for result in results:
            assert result is not None

    @pytest.mark.asyncio
    async def test_large_order_history(self, api):
        """Test retrieving large order history."""
        email = list(api.customers.keys())[0]

        # Test with large limit
        orders = await api.get_customer_orders(email, limit=1000)

        # Should handle gracefully (return what's available)
        assert isinstance(orders, list)
        assert len(orders) >= 0

    @pytest.mark.asyncio
    async def test_response_time_consistency(self, api):
        """Test that response times are consistent."""
        import time

        email = list(api.customers.keys())[0]
        times = []

        # Make multiple requests and measure time
        for _ in range(5):
            start_time = time.time()
            await api.get_customer_by_email(email)
            elapsed_time = time.time() - start_time
            times.append(elapsed_time)

        # Times should be reasonably consistent (within 50ms of each other)
        max_time = max(times)
        min_time = min(times)
        assert max_time - min_time < 0.05  # 50ms difference max
