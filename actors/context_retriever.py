"""
Context Retriever Actor for the Actor Mesh Demo.

This actor retrieves customer context data from various APIs and services,
enriching messages with customer profile, order history, and related information.
"""

import asyncio
import logging

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from models.message import MessagePayload
from storage.redis_client import get_redis_client

from actors.base import ProcessorActor


class ContextRetriever(ProcessorActor):
    """
    Processor actor that retrieves and caches customer context data.

    Fetches customer profile, order history, support history, and tracking
    information from mock APIs and caches results for performance.
    """

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        customer_api_url: str = "http://localhost:8001",
        orders_api_url: str = "http://localhost:8002",
        tracking_api_url: str = "http://localhost:8003",
    ):
        """Initialize the Context Retriever actor."""
        super().__init__("context_retriever", nats_url)

        self.customer_api_url = customer_api_url
        self.orders_api_url = orders_api_url
        self.tracking_api_url = tracking_api_url

        # HTTP client configuration
        self.timeout = 10.0
        self.max_retries = 2

        # Cache configuration
        self.cache_ttl = 300  # 5 minutes
        self.profile_cache_ttl = 1800  # 30 minutes for profile data

    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Retrieve customer context data.

        Args:
            payload: Message payload containing customer email

        Returns:
            Dictionary with customer context data
        """
        try:
            customer_email = payload.customer_email

            # Check cache first
            redis_client = await get_redis_client()
            cached_context = await redis_client.get_context(customer_email)

            if cached_context:
                self.logger.info(f"Retrieved cached context for {customer_email}")
                return {
                    "customer_context": cached_context,
                    "source": "cache",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }

            # Fetch fresh context data
            context = await self._fetch_customer_context(customer_email)

            if context:
                # Cache the context
                await redis_client.set_context(customer_email, context)

                self.logger.info(f"Retrieved fresh context for {customer_email}")
                return {
                    "customer_context": context,
                    "source": "api",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                self.logger.warning(f"No context found for {customer_email}")
                return {
                    "customer_context": {"error": "Customer not found"},
                    "source": "error",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }

        except Exception as e:
            self.logger.error(f"Error retrieving customer context: {e}")
            return {
                "customer_context": {"error": str(e)},
                "source": "error",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich payload with customer context."""
        payload.context = result

    async def _fetch_customer_context(self, customer_email: str) -> Optional[Dict[str, Any]]:
        """
        Fetch complete customer context from all APIs.

        Args:
            customer_email: Customer email address

        Returns:
            Combined context data or None if customer not found
        """
        context = {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Fetch customer profile
            profile = await self._fetch_customer_profile(client, customer_email)
            if not profile:
                return None

            context["profile"] = profile

            # Fetch order history
            orders = await self._fetch_order_history(client, customer_email)
            context["orders"] = orders

            # Fetch support history if we have customer_id
            customer_id = profile.get("customer_id")
            if customer_id:
                support_history = await self._fetch_support_history(client, customer_id)
                context["support_history"] = support_history

            # Fetch tracking information for recent orders
            tracking_info = await self._fetch_tracking_info(client, orders)
            context["tracking"] = tracking_info

            # Add summary statistics
            context["summary"] = self._generate_context_summary(profile, orders, support_history)

        return context

    async def _fetch_customer_profile(self, client: httpx.AsyncClient, email: str) -> Optional[Dict[str, Any]]:
        """Fetch customer profile from Customer API."""
        try:
            url = f"{self.customer_api_url}/customers/{email}"
            response = await client.get(url)

            if response.status_code == 200:
                profile = await response.json()
                self.logger.debug(f"Retrieved profile for {email}")
                return profile
            elif response.status_code == 404:
                self.logger.warning(f"Customer profile not found: {email}")
                return None
            else:
                self.logger.error(f"Error fetching profile: {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"Exception fetching customer profile: {e}")
            return None

    async def _fetch_order_history(self, client: httpx.AsyncClient, email: str) -> List[Dict[str, Any]]:
        """Fetch order history from Orders API."""
        try:
            url = f"{self.orders_api_url}/customers/{email}/orders"
            response = await client.get(url, params={"limit": 10})

            if response.status_code == 200:
                orders_response = await response.json()
                orders = orders_response.get("orders", [])
                self.logger.debug(f"Retrieved {len(orders)} orders for {email}")
                return orders
            else:
                self.logger.warning(f"Error fetching orders: {response.status_code}")
                return []

        except Exception as e:
            self.logger.error(f"Exception fetching order history: {e}")
            return []

    async def _fetch_support_history(self, client: httpx.AsyncClient, customer_id: str) -> List[Dict[str, Any]]:
        """Fetch support history from Customer API."""
        try:
            url = f"{self.customer_api_url}/customers/{customer_id}/support-history"
            response = await client.get(url, params={"limit": 5})

            if response.status_code == 200:
                history_response = await response.json()
                # Handle both list and dict responses
                if isinstance(history_response, list):
                    history = history_response
                else:
                    history = history_response.get("support_history", [])
                self.logger.debug(f"Retrieved {len(history)} support interactions for {customer_id}")
                return history
            else:
                self.logger.warning(f"Error fetching support history: {response.status_code}")
                return []

        except Exception as e:
            self.logger.error(f"Exception fetching support history: {e}")
            return []

    async def _fetch_tracking_info(
        self, client: httpx.AsyncClient, orders: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fetch tracking information for recent orders."""
        tracking_info = []

        # Get tracking info for orders with tracking numbers
        recent_orders = [order for order in orders[:3] if order.get("tracking_number")]

        for order in recent_orders:
            tracking_number = order["tracking_number"]
            try:
                url = f"{self.tracking_api_url}/tracking/{tracking_number}"
                response = await client.get(url)

                if response.status_code == 200:
                    tracking_data = await response.json()
                    tracking_info.append(
                        {
                            "order_id": order["order_id"],
                            "tracking_number": tracking_number,
                            "status": tracking_data.get("current_status"),
                            "estimated_delivery": tracking_data.get("estimated_delivery"),
                            "last_event": tracking_data.get("tracking_events", [])[-1]
                            if tracking_data.get("tracking_events")
                            else None,
                        }
                    )
                    self.logger.debug(f"Retrieved tracking info for {tracking_number}")

            except Exception as e:
                self.logger.warning(f"Error fetching tracking info for {tracking_number}: {e}")

        return tracking_info

    def _generate_context_summary(
        self, profile: Dict[str, Any], orders: List[Dict[str, Any]], support_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate summary statistics from context data."""
        summary = {
            "customer_tier": profile.get("tier", "standard"),
            "account_status": profile.get("account_status", "active"),
            "total_orders": len(orders),
            "recent_order_count": 0,
            "total_spent": 0.0,
            "average_order_value": 0.0,
            "last_order_date": None,
            "support_interactions": len(support_history),
            "recent_complaints": 0,
            "customer_satisfaction": "unknown",
            "risk_factors": [],
        }

        if orders:
            # Calculate order statistics
            recent_cutoff = datetime.now() - timedelta(days=90)
            recent_orders = []
            total_spent = 0.0

            for order in orders:
                try:
                    order_date = datetime.fromisoformat(order["order_date"])
                    if order_date > recent_cutoff:
                        recent_orders.append(order)
                    total_spent += order.get("total_amount", 0.0)
                except (ValueError, KeyError):
                    continue

            summary["recent_order_count"] = len(recent_orders)
            summary["total_spent"] = round(total_spent, 2)
            summary["average_order_value"] = round(total_spent / len(orders), 2) if orders else 0.0
            summary["last_order_date"] = orders[0].get("order_date") if orders else None

        if support_history:
            # Analyze support history
            recent_complaints = [
                interaction
                for interaction in support_history
                if interaction.get("type") == "complaint"
                and interaction.get("created_date")
                and datetime.fromisoformat(interaction["created_date"]) > datetime.now() - timedelta(days=30)
            ]

            summary["recent_complaints"] = len(recent_complaints)

            # Determine satisfaction based on recent interactions
            recent_interactions = [
                interaction
                for interaction in support_history
                if interaction.get("created_date")
                and datetime.fromisoformat(interaction["created_date"]) > datetime.now() - timedelta(days=90)
            ]

            if recent_interactions:
                complaint_ratio = len([i for i in recent_interactions if i.get("type") == "complaint"]) / len(
                    recent_interactions
                )
                if complaint_ratio > 0.5:
                    summary["customer_satisfaction"] = "low"
                elif complaint_ratio > 0.2:
                    summary["customer_satisfaction"] = "medium"
                else:
                    summary["customer_satisfaction"] = "high"

        # Identify risk factors
        risk_factors = []

        if summary["recent_complaints"] > 2:
            risk_factors.append("multiple_recent_complaints")

        if summary["customer_satisfaction"] == "low":
            risk_factors.append("low_satisfaction")

        if profile.get("account_status") == "suspended":
            risk_factors.append("suspended_account")

        # Check for delivery issues in tracking
        if hasattr(self, "_tracking_info"):
            delivery_issues = [
                track for track in self._tracking_info if track.get("status") in ["exception", "delayed"]
            ]
            if delivery_issues:
                risk_factors.append("delivery_issues")

        summary["risk_factors"] = risk_factors

        return summary

    async def invalidate_customer_cache(self, customer_email: str) -> bool:
        """
        Invalidate cached customer context.

        Args:
            customer_email: Customer email to invalidate

        Returns:
            True if cache was cleared
        """
        try:
            redis_client = await get_redis_client()
            return await redis_client.delete_context(customer_email)
        except Exception as e:
            self.logger.error(f"Error invalidating cache for {customer_email}: {e}")
            return False

    async def update_customer_context(self, customer_email: str, updates: Dict[str, Any]) -> bool:
        """
        Update specific fields in customer context cache.

        Args:
            customer_email: Customer email
            updates: Dictionary of updates to apply

        Returns:
            True if update was successful
        """
        try:
            redis_client = await get_redis_client()
            await redis_client.update_context(customer_email, updates)
            return True
        except Exception as e:
            self.logger.error(f"Error updating context for {customer_email}: {e}")
            return False


# Factory function for creating the actor
def create_context_retriever(
    nats_url: str = "nats://localhost:4222",
    customer_api_url: str = "http://localhost:8001",
    orders_api_url: str = "http://localhost:8002",
    tracking_api_url: str = "http://localhost:8003",
) -> ContextRetriever:
    """Create a ContextRetriever actor instance."""
    return ContextRetriever(nats_url, customer_api_url, orders_api_url, tracking_api_url)


# Main execution for standalone testing
async def main():
    """Main function for testing the context retriever."""
    logging.basicConfig(level=logging.INFO)

    # Create and start the actor
    retriever = ContextRetriever()

    try:
        await retriever.start()
        print("Context Retriever started successfully")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await retriever.stop()


if __name__ == "__main__":
    asyncio.run(main())
