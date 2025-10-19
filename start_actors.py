#!/usr/bin/env python3
"""
Start all actors for the Actor Mesh Demo.

This script starts all the required actors for the e-commerce support agent
system, avoiding the module import issues that occur with python -m execution.
"""

import asyncio
import logging
import signal
import sys
from typing import List

# Import all the actor classes
from actors.sentiment_analyzer import SentimentAnalyzer
from actors.intent_analyzer import IntentAnalyzer
from actors.context_retriever import ContextRetriever
from actors.decision_router import DecisionRouter
from actors.response_generator import ResponseGenerator
from actors.guardrail_validator import GuardrailValidator
from actors.execution_coordinator import ExecutionCoordinator
from actors.escalation_router import EscalationRouter
from actors.response_aggregator import ResponseAggregator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ActorManager:
    """Manages all actors for the system."""

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.actors: List = []
        self.running = False

        # Create all actors
        self.actors = [
            SentimentAnalyzer(nats_url),
            IntentAnalyzer(nats_url),
            ContextRetriever(nats_url),
            DecisionRouter(nats_url),
            ResponseGenerator(nats_url),
            GuardrailValidator(nats_url),
            ExecutionCoordinator(nats_url),
            EscalationRouter(nats_url),
            ResponseAggregator(nats_url),
        ]

    async def start_all(self):
        """Start all actors."""
        logger.info("Starting all actors...")

        tasks = []
        for actor in self.actors:
            try:
                await actor.start()
                logger.info(f"✅ Started {actor.name}")
            except Exception as e:
                logger.error(f"❌ Failed to start {actor.name}: {e}")
                raise

        self.running = True
        logger.info(f"🚀 All {len(self.actors)} actors started successfully!")

    async def stop_all(self):
        """Stop all actors."""
        logger.info("Stopping all actors...")
        self.running = False

        tasks = []
        for actor in self.actors:
            try:
                await actor.stop()
                logger.info(f"🛑 Stopped {actor.name}")
            except Exception as e:
                logger.error(f"⚠️ Error stopping {actor.name}: {e}")

        logger.info("All actors stopped")

    async def run_forever(self):
        """Keep the actors running until interrupted."""
        await self.start_all()

        try:
            logger.info("📡 Actors are running... Press Ctrl+C to stop.")
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🔔 Received interrupt signal")
        finally:
            await self.stop_all()

async def main():
    """Main function to start and manage all actors."""
    nats_url = "nats://localhost:4222"

    # Handle command line arguments
    if len(sys.argv) > 1:
        nats_url = sys.argv[1]

    manager = ActorManager(nats_url)

    # Set up signal handlers
    def signal_handler():
        logger.info("🛑 Received shutdown signal")
        manager.running = False

    # Handle SIGINT and SIGTERM
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in [signal.SIGINT, signal.SIGTERM]:
            loop.add_signal_handler(sig, signal_handler)

    try:
        await manager.run_forever()
    except Exception as e:
        logger.error(f"💥 Error in main: {e}")
        await manager.stop_all()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)
