#!/usr/bin/env python3
"""
Test script for conversation context functionality.

This script tests:
1. Session persistence across multiple messages
2. Entity tracking (order numbers, issues)
3. Context maintenance in responses
4. Multi-turn conversations
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from storage.sqlite_client import init_sqlite, get_sqlite_client


class ConversationContextTester:
    """Test conversation context functionality."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id = None
        self.customer_email = "test@example.com"
        self.test_results = []

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        result = {
            "test": test_name,
            "status": status,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        print(f"{status}: {test_name}")
        if details:
            print(f"   {details}")

    async def send_message(self, message: str) -> dict:
        """Send a message via HTTP API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": message,
                        "customer_email": self.customer_email,
                        "session_id": self.session_id
                    }
                )
                response.raise_for_status()
                data = response.json()

                # Store session_id for subsequent messages
                if not self.session_id and "session_id" in data:
                    self.session_id = data["session_id"]
                    print(f"   Session ID: {self.session_id}")

                return data
        except Exception as e:
            print(f"   ❌ Error sending message: {e}")
            return {"error": str(e)}

    async def test_session_persistence(self):
        """Test 1: Session ID persistence across messages."""
        print("\n" + "="*80)
        print("TEST 1: Session Persistence")
        print("="*80)

        # Message 1
        print("\n📤 Sending: 'I have an issue with my order'")
        response1 = await self.send_message("I have an issue with my order")

        if "error" in response1:
            self.log_result("Session Persistence - Message 1", False, response1.get("error"))
            return

        session_id_1 = self.session_id
        print(f"📥 Response: {response1.get('response', 'N/A')[:100]}...")

        # Message 2
        await asyncio.sleep(1)
        print("\n📤 Sending: 'My order number is ord-12345'")
        response2 = await self.send_message("My order number is ord-12345")

        if "error" in response2:
            self.log_result("Session Persistence - Message 2", False, response2.get("error"))
            return

        session_id_2 = self.session_id
        print(f"📥 Response: {response2.get('response', 'N/A')[:100]}...")

        # Check if session IDs match
        passed = session_id_1 == session_id_2
        self.log_result(
            "Session Persistence",
            passed,
            f"Session IDs: {session_id_1[:20]}... == {session_id_2[:20]}..."
        )

    async def test_entity_tracking(self):
        """Test 2: Entity tracking (order number maintenance)."""
        print("\n" + "="*80)
        print("TEST 2: Entity Tracking (Order Number)")
        print("="*80)

        # Message 3: Ask about order without mentioning number
        await asyncio.sleep(1)
        print("\n📤 Sending: 'What is the status of my order?'")
        response3 = await self.send_message("What is the status of my order?")

        if "error" in response3:
            self.log_result("Entity Tracking", False, response3.get("error"))
            return

        agent_response = response3.get('response', '')
        print(f"📥 Response: {agent_response[:200]}...")

        # Check if agent uses the order number without asking
        has_order_ref = any(ref in agent_response.lower() for ref in ['ord-12345', '12345', 'order #12345'])
        asks_for_order = any(phrase in agent_response.lower() for phrase in [
            'order number', 'provide your order', 'which order', 'what order'
        ])

        passed = has_order_ref and not asks_for_order
        details = []
        if has_order_ref:
            details.append("✓ References order number")
        else:
            details.append("✗ Doesn't reference order number")
        if not asks_for_order:
            details.append("✓ Doesn't ask for order number")
        else:
            details.append("✗ Asks for order number again")

        self.log_result("Entity Tracking", passed, " | ".join(details))

    async def test_context_maintenance(self):
        """Test 3: Context maintenance across conversation."""
        print("\n" + "="*80)
        print("TEST 3: Context Maintenance")
        print("="*80)

        # Message 4: Mention issue
        await asyncio.sleep(1)
        print("\n📤 Sending: 'The package arrived damaged'")
        response4 = await self.send_message("The package arrived damaged")

        if "error" in response4:
            self.log_result("Context Maintenance - Issue Report", False, response4.get("error"))
            return

        print(f"📥 Response: {response4.get('response', 'N/A')[:200]}...")

        # Message 5: Follow-up without context
        await asyncio.sleep(1)
        print("\n📤 Sending: 'When will the replacement arrive?'")
        response5 = await self.send_message("When will the replacement arrive?")

        if "error" in response5:
            self.log_result("Context Maintenance - Follow-up", False, response5.get("error"))
            return

        agent_response = response5.get('response', '')
        print(f"📥 Response: {agent_response[:200]}...")

        # Check if agent maintains context of damaged package
        understands_context = any(word in agent_response.lower() for word in [
            'replacement', 'damaged', 'new', 'order', '12345'
        ])
        asks_basic_questions = any(phrase in agent_response.lower() for phrase in [
            'what issue', 'what problem', 'order number?', 'which order'
        ])

        passed = understands_context and not asks_basic_questions
        details = []
        if understands_context:
            details.append("✓ Understands replacement context")
        else:
            details.append("✗ Lost context of damaged package")
        if not asks_basic_questions:
            details.append("✓ Doesn't ask basic questions")
        else:
            details.append("✗ Asks for information already provided")

        self.log_result("Context Maintenance", passed, " | ".join(details))

    async def test_no_customer_email_in_response(self):
        """Test 4: Check that customer email is not used as contact."""
        print("\n" + "="*80)
        print("TEST 4: Contact Information")
        print("="*80)

        # Check all previous responses
        sqlite_client = await get_sqlite_client()
        messages = await sqlite_client.get_messages(self.session_id, limit=20)

        agent_messages = [msg for msg in messages if msg.message_type == "agent"]

        has_customer_email_error = False
        has_proper_contact = False

        for msg in agent_messages:
            content = msg.content.lower()

            # Check if customer email is used as contact
            if self.customer_email.lower() in content:
                if any(phrase in content for phrase in ['reach out', 'contact', 'email me']):
                    has_customer_email_error = True
                    print(f"   ⚠️  Found customer email in response: {msg.content[:100]}...")

            # Check if proper contact info is used
            if any(contact in content for contact in ['support@', 'techmart', '1-800', 'customer support']):
                has_proper_contact = True

        passed = not has_customer_email_error
        details = []
        if not has_customer_email_error:
            details.append("✓ Customer email not used as contact")
        else:
            details.append("✗ Customer email used as contact method")
        if has_proper_contact:
            details.append("✓ Proper contact info provided")

        self.log_result("Contact Information", passed, " | ".join(details))

    async def check_database_consistency(self):
        """Test 5: Check database for session consistency."""
        print("\n" + "="*80)
        print("TEST 5: Database Consistency")
        print("="*80)

        sqlite_client = await get_sqlite_client()

        # Get all messages for this session
        messages = await sqlite_client.get_messages(self.session_id, limit=50)

        print(f"\n📊 Found {len(messages)} messages in database")

        customer_count = sum(1 for msg in messages if msg.message_type == "customer")
        agent_count = sum(1 for msg in messages if msg.message_type == "agent")

        print(f"   Customer messages: {customer_count}")
        print(f"   Agent messages: {agent_count}")

        # Check for duplicates
        contents = [msg.content for msg in messages]
        duplicates = len(contents) - len(set(contents))

        passed = duplicates == 0 and customer_count > 0 and agent_count > 0
        details = []
        if duplicates == 0:
            details.append("✓ No duplicate messages")
        else:
            details.append(f"✗ Found {duplicates} duplicate messages")
        if customer_count > 0 and agent_count > 0:
            details.append("✓ Both customer and agent messages present")

        self.log_result("Database Consistency", passed, " | ".join(details))

        # Show conversation flow
        print("\n📜 Conversation Flow:")
        for i, msg in enumerate(messages, 1):
            icon = "👤" if msg.message_type == "customer" else "🤖"
            print(f"   {i}. {icon} {msg.content[:80]}...")

    async def run_all_tests(self):
        """Run all tests."""
        print("\n" + "="*80)
        print("🧪 CONVERSATION CONTEXT TEST SUITE")
        print("="*80)
        print(f"Base URL: {self.base_url}")
        print(f"Customer: {self.customer_email}")
        print(f"Time: {datetime.now().isoformat()}")

        try:
            # Initialize storage
            await init_sqlite()

            # Run tests
            await self.test_session_persistence()
            await self.test_entity_tracking()
            await self.test_context_maintenance()
            await self.test_no_customer_email_in_response()
            await self.check_database_consistency()

            # Summary
            print("\n" + "="*80)
            print("📊 TEST SUMMARY")
            print("="*80)

            passed = sum(1 for r in self.test_results if r["passed"])
            total = len(self.test_results)

            for result in self.test_results:
                print(f"{result['status']}: {result['test']}")
                if result['details']:
                    print(f"   {result['details']}")

            print(f"\n{'='*80}")
            if passed == total:
                print(f"✅ ALL TESTS PASSED ({passed}/{total})")
            else:
                print(f"⚠️  {passed}/{total} TESTS PASSED, {total - passed} FAILED")
            print(f"{'='*80}\n")

            return passed == total

        except Exception as e:
            print(f"\n❌ Test suite failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main test function."""
    import argparse

    parser = argparse.ArgumentParser(description="Test conversation context functionality")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL for API")
    parser.add_argument("--email", default="test@example.com", help="Test customer email")

    args = parser.parse_args()

    tester = ConversationContextTester(base_url=args.url)
    tester.customer_email = args.email

    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
