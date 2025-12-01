#!/usr/bin/env python3
"""
Diagnostic script to check conversation history in SQLite database.

This script helps diagnose conversation context issues by:
1. Showing all sessions and their message counts
2. Displaying the actual conversation history for a session
3. Checking for session ID consistency issues
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.sqlite_client import get_sqlite_client


async def check_all_sessions():
    """Display all sessions in the database."""
    print("\n" + "="*80)
    print("ALL CONVERSATION SESSIONS")
    print("="*80 + "\n")

    sqlite_client = await get_sqlite_client()

    # Get customer history stats instead
    import aiosqlite
    async with aiosqlite.connect(sqlite_client.db_path) as db:
        cursor = await db.execute("""
            SELECT session_id, customer_email, created_at, updated_at,
                   message_count, status, issue_type
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT 50
        """)
        conversations = await cursor.fetchall()

    if not conversations:
        print("❌ No conversations found in database!")
        return

    print(f"Found {len(conversations)} conversation sessions:\n")

    for conv in conversations:
        session_id, customer_email, created_at, updated_at, msg_count, status, issue_type = conv
        print(f"📧 Session: {session_id[:30]}...")
        print(f"   Customer: {customer_email}")
        print(f"   Messages: {msg_count}")
        print(f"   Created: {created_at}")
        print(f"   Updated: {updated_at}")
        print(f"   Status: {status} | Issue: {issue_type}")
        print()


async def check_session_messages(session_id: str = None):
    """Display messages for a specific session or the most recent session."""
    print("\n" + "="*80)
    print("SESSION MESSAGE HISTORY")
    print("="*80 + "\n")

    sqlite_client = await get_sqlite_client()

    if session_id:
        print(f"Checking session: {session_id}\n")
    else:
        # Get the most recent session
        import aiosqlite
        async with aiosqlite.connect(sqlite_client.db_path) as db:
            cursor = await db.execute("""
                SELECT session_id FROM conversations
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            result = await cursor.fetchone()

        if not result:
            print("❌ No sessions found in database!")
            return

        session_id = result[0]
        print(f"Checking most recent session: {session_id}\n")

    # Get messages for this session
    messages = await sqlite_client.get_messages(session_id, limit=100)

    if not messages:
        print(f"❌ No messages found for session: {session_id}")
        return

    print(f"Found {len(messages)} messages:\n")

    for i, msg in enumerate(messages, 1):
        icon = "👤" if msg.message_type == "customer" else "🤖"
        print(f"{i}. {icon} {msg.message_type.upper()} ({msg.created_at})")
        print(f"   {msg.content}")

        if msg.metadata:
            print(f"   Metadata: {msg.metadata}")

        print()


async def check_customer_history(customer_email: str):
    """Display all sessions and messages for a specific customer."""
    print("\n" + "="*80)
    print(f"CUSTOMER HISTORY: {customer_email}")
    print("="*80 + "\n")

    sqlite_client = await get_sqlite_client()

    # Get customer stats
    stats = await sqlite_client.get_customer_history(customer_email)

    if not stats:
        print(f"❌ No history found for customer: {customer_email}")
        return

    print(f"Found {len(stats)} session(s) for this customer:\n")

    for stat in stats:
        print(f"📧 Session: {stat['session_id'][:30]}...")
        print(f"   Messages: {stat['message_count']}")
        print(f"   Created: {stat['created_at']}")
        print(f"   Updated: {stat['last_updated']}")
        print(f"   Status: {stat['status']} | Issue: {stat['issue_type']}")
        print()

        # Get messages for this session
        messages = await sqlite_client.get_messages(stat['session_id'], limit=100)

        for i, msg in enumerate(messages, 1):
            icon = "👤" if msg.message_type == "customer" else "🤖"
            print(f"   {i}. {icon} {msg.content[:80]}...")

        print()


async def check_session_id_consistency():
    """Check for session ID fragmentation issues."""
    print("\n" + "="*80)
    print("SESSION ID CONSISTENCY CHECK")
    print("="*80 + "\n")

    sqlite_client = await get_sqlite_client()

    # Check for customers with multiple sessions
    import aiosqlite
    async with aiosqlite.connect(sqlite_client.db_path) as db:
        cursor = await db.execute("""
            SELECT customer_email, COUNT(DISTINCT session_id) as session_count,
                   COUNT(*) as total_conversations
            FROM conversations
            GROUP BY customer_email
            HAVING session_count > 1
            ORDER BY session_count DESC
        """)
        fragmented = await cursor.fetchall()

    if not fragmented:
        print("✅ No session fragmentation detected - all customers have single sessions")
        return

    print(f"⚠️  Found {len(fragmented)} customers with multiple sessions:\n")

    for customer_email, session_count, total_conv in fragmented:
        print(f"📧 {customer_email}")
        print(f"   Sessions: {session_count} (should be 1 if session persistence working)")
        print(f"   Total conversations: {total_conv}")

        # Get session details
        async with aiosqlite.connect(sqlite_client.db_path) as db:
            cursor2 = await db.execute("""
                SELECT session_id, message_count, created_at, updated_at
                FROM conversations
                WHERE customer_email = ?
                ORDER BY created_at
            """, (customer_email,))
            sessions = await cursor2.fetchall()

        for session_id, msg_count, created, updated in sessions:
            print(f"      - {session_id[:40]}... ({msg_count} msgs, {created})")

        print()


async def check_recent_conversations():
    """Display the most recent conversations with full context."""
    print("\n" + "="*80)
    print("RECENT CONVERSATIONS (Last 5)")
    print("="*80 + "\n")

    sqlite_client = await get_sqlite_client()

    # Get recent sessions
    import aiosqlite
    async with aiosqlite.connect(sqlite_client.db_path) as db:
        cursor = await db.execute("""
            SELECT session_id, customer_email, message_count, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT 5
        """)
        sessions = await cursor.fetchall()

    if not sessions:
        print("❌ No conversations found!")
        return

    for session_id, customer_email, msg_count, updated_at in sessions:
        print(f"\n{'='*60}")
        print(f"Session: {session_id[:40]}...")
        print(f"Customer: {customer_email}")
        print(f"Updated: {updated_at}")
        print(f"Messages: {msg_count}")
        print(f"{'='*60}\n")

        # Get messages
        messages = await sqlite_client.get_messages(session_id, limit=20)

        for msg in messages:
            icon = "👤 USER" if msg.message_type == "customer" else "🤖 AGENT"
            timestamp = msg.created_at.split('.')[0] if '.' in msg.created_at else msg.created_at
            print(f"{icon} [{timestamp}]:")
            print(f"  {msg.content}\n")


async def main():
    """Main diagnostic function."""
    import argparse

    parser = argparse.ArgumentParser(description="Check conversation history in database")
    parser.add_argument("--all", action="store_true", help="Show all sessions")
    parser.add_argument("--session", type=str, help="Show messages for specific session ID")
    parser.add_argument("--customer", type=str, help="Show history for specific customer email")
    parser.add_argument("--consistency", action="store_true", help="Check session ID consistency")
    parser.add_argument("--recent", action="store_true", help="Show recent conversations")

    args = parser.parse_args()

    # If no arguments provided, show recent conversations
    if not any([args.all, args.session, args.customer, args.consistency, args.recent]):
        args.recent = True

    try:
        # Initialize storage
        from storage.sqlite_client import init_sqlite
        await init_sqlite()

        if args.all:
            await check_all_sessions()

        if args.session:
            await check_session_messages(args.session)

        if args.customer:
            await check_customer_history(args.customer)

        if args.consistency:
            await check_session_id_consistency()

        if args.recent:
            await check_recent_conversations()

        print("\n" + "="*80)
        print("✅ Diagnostic check complete")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ Error during diagnostic check: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
