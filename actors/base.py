"""
Base Actor Framework for the Actor Mesh Demo.

This module provides the foundation for all actors in the e-commerce support
agent system, implementing NATS-based communication and message routing.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set

import nats
from models.message import Message, MessagePayload
from nats.js import JetStreamContext
from nats.aio.msg import Msg


class BaseActor(ABC):
    """Base class for all actors in the system."""

    def __init__(self, name: str, nats_url: str = "nats://localhost:4222") -> None:
        """
        Initialize the base actor.

        Args:
            name: Actor name (used for NATS subject)
            nats_url: NATS server URL
        """
        self.name: str = name
        self.nats_url: str = nats_url
        self.subject: str = f"ecommerce.support.{name}"

        # NATS connections
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None

        # Configuration
        self.max_retries: int = 3
        self.retry_delay: float = 1.0
        self.processing_timeout: float = 30.0

        # Setup logging
        self.logger: logging.Logger = logging.getLogger(f"actor.{name}")
        self.logger.setLevel(logging.INFO)

        # Runtime state
        self._running: bool = False
        self._tasks: Set[asyncio.Task[Any]] = set()

    async def start(self) -> None:
        """Start the actor and begin listening for messages."""
        if self._running:
            self.logger.warning("Actor already running")
            return

        try:
            # Connect to NATS
            self.logger.info(f"Connecting to NATS at {self.nats_url}")
            self.nc = await nats.connect(self.nats_url)
            if self.nc is not None:
                self.js = self.nc.jetstream()

            # Ensure stream exists
            await self._ensure_stream()

            # Subscribe to messages
            await self._subscribe()

            self._running = True
            self.logger.info(f"Actor '{self.name}' started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start actor: {e}")
            raise

    async def stop(self) -> None:
        """Stop the actor and cleanup resources."""
        if not self._running:
            return

        self.logger.info(f"Stopping actor '{self.name}'")
        self._running = False

        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close NATS connection
        if self.nc:
            await self.nc.close()

        self.logger.info(f"Actor '{self.name}' stopped")

    async def _ensure_stream(self) -> None:
        """Ensure the JetStream stream exists."""
        if self.js is None:
            raise RuntimeError("JetStream not initialized")

        stream_name: str = "ECOMMERCE_SUPPORT"
        subjects: list[str] = ["ecommerce.support.*"]

        try:
            # Try to get existing stream info
            await self.js.stream_info(stream_name)
            self.logger.debug(f"Stream '{stream_name}' already exists")
        except Exception:
            # Stream doesn't exist, create it
            self.logger.info(f"Creating stream '{stream_name}'")
            await self.js.add_stream(
                name=stream_name,
                subjects=subjects,
                retention="workqueue",
                max_age=3600,  # 1 hour retention
            )

    async def _subscribe(self) -> None:
        """Subscribe to NATS messages for this actor."""
        if self.js is None:
            raise RuntimeError("JetStream not initialized")

        try:
            await self.js.subscribe(
                self.subject,
                cb=self._handle_message_wrapper,
                durable=f"{self.name}_durable",
                manual_ack=True,
            )
            self.logger.info(f"Subscribed to subject: {self.subject}")
        except Exception as e:
            self.logger.error(f"Failed to subscribe: {e}")
            raise

    async def _handle_message_wrapper(self, msg: Msg) -> None:
        """Wrapper for message handling with error management."""
        # Create a task for processing
        task: asyncio.Task[None] = asyncio.create_task(self._process_message(msg))
        self._tasks.add(task)

        # Cleanup completed task
        task.add_done_callback(self._tasks.discard)

    async def _process_message(self, msg: Msg) -> None:
        """Process incoming NATS message."""
        message_obj: Optional[Message] = None

        try:
            # Deserialize message
            message_data: Dict[str, Any] = json.loads(msg.data.decode())
            message_obj = Message(**message_data)

            self.logger.info(f"Processing message {message_obj.message_id} for session {message_obj.session_id}")

            # Check if this is the correct step in the route
            current_actor: Optional[str] = message_obj.route.get_current_actor()
            if current_actor != self.name:
                self.logger.warning(f"Received message for wrong actor. Expected: {current_actor}, Got: {self.name}")
                await msg.nak()
                return

            # Process the message payload
            result: Optional[Dict[str, Any]] = await asyncio.wait_for(
                self.process(message_obj.payload), timeout=self.processing_timeout
            )

            # Add processing result to message
            if result:
                await self._enrich_payload(message_obj.payload, result)

            # Route to next actor or complete
            await self._route_to_next(message_obj)

            # Acknowledge successful processing
            await msg.ack()

            self.logger.info(f"Successfully processed message {message_obj.message_id}")

        except asyncio.TimeoutError:
            self.logger.error(f"Processing timeout for message {message_obj.message_id if message_obj else 'unknown'}")
            await self._handle_error(msg, message_obj, "timeout", "Processing timeout")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await self._handle_error(msg, message_obj, "processing_error", str(e))

    async def _handle_error(self, msg: Msg, message_obj: Optional[Message], error_type: str, error_message: str) -> None:
        """Handle processing errors with retry logic."""
        try:
            if not message_obj:
                # Can't recover without message object
                await msg.nak()
                return

            # Check retry count
            retry_count: int = message_obj.metadata.get("retry_count", 0)
            if retry_count >= self.max_retries:
                self.logger.error(
                    f"Max retries exceeded for message {message_obj.message_id}, routing to error handler"
                )
                await self._route_to_error_handler(message_obj, error_type, error_message)
                await msg.ack()  # Don't reprocess
                return

            # Increment retry counter and add error info
            message_obj.increment_retry()
            message_obj.add_error(error_type, error_message, self.name)

            # Delay before retry
            await asyncio.sleep(self.retry_delay * (retry_count + 1))

            # Requeue message for retry
            await msg.nak()

        except Exception as e:
            self.logger.error(f"Error in error handler: {e}")
            await msg.nak()

    async def _route_to_next(self, message: Message) -> None:
        """Route message to the next actor in the flow."""
        if self.js is None:
            raise RuntimeError("JetStream not initialized")

        # Advance to next step
        if message.route.advance():
            next_actor: Optional[str] = message.route.get_current_actor()
            if next_actor:
                next_subject: str = f"ecommerce.support.{next_actor}"
                await self.js.publish(next_subject, json.dumps(message.dict()).encode())
                self.logger.debug(f"Routed message to {next_actor}")
        else:
            # Route complete
            self.logger.info(f"Message {message.message_id} completed processing")

    async def _route_to_error_handler(self, message: Message, error_type: str, error_message: str) -> None:
        """Route message to error handler."""
        if self.js is None:
            raise RuntimeError("JetStream not initialized")

        if message.route.error_handler:
            error_subject: str = f"ecommerce.support.{message.route.error_handler}"
            message.add_error(error_type, error_message, self.name)

            await self.js.publish(error_subject, json.dumps(message.dict()).encode())
            self.logger.info(f"Routed error message to {message.route.error_handler}")

    async def _enrich_payload(self, payload: MessagePayload, result: Dict[str, Any]) -> None:
        """Enrich the payload with processing results."""
        # Default implementation - subclasses should override for specific enrichment
        pass

    async def send_message(self, subject: str, message: Message) -> None:
        """Send a message to a specific subject."""
        if self.js is None:
            raise RuntimeError("Actor not started")

        await self.js.publish(subject, json.dumps(message.dict()).encode())

    @abstractmethod
    async def process(self, payload: MessagePayload) -> Optional[Dict[str, Any]]:
        """
        Process the message payload.

        Args:
            payload: The message payload to process

        Returns:
            Optional processing result to be added to the payload
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', running={self._running})"


class ProcessorActor(BaseActor):
    """Base class for naive processor actors that perform simple transformations."""

    def __init__(self, name: str, nats_url: str = "nats://localhost:4222") -> None:
        super().__init__(name, nats_url)


class RouterActor(BaseActor):
    """Base class for smart router actors that make routing decisions."""

    def __init__(self, name: str, nats_url: str = "nats://localhost:4222") -> None:
        super().__init__(name, nats_url)

    async def _route_to_next(self, message: Message) -> None:
        """Override to implement custom routing logic."""
        # Router actors implement their own routing logic
        await self.route_message(message)

    @abstractmethod
    async def route_message(self, message: Message) -> None:
        """
        Route message based on content and processing results.

        Args:
            message: The message to route
        """
        raise NotImplementedError


# Utility functions for actor management
async def start_multiple_actors(actors: list[BaseActor]) -> None:
    """Start multiple actors concurrently."""
    tasks: list[asyncio.Task[None]] = [asyncio.create_task(actor.start()) for actor in actors]
    await asyncio.gather(*tasks)


async def stop_multiple_actors(actors: list[BaseActor]) -> None:
    """Stop multiple actors concurrently."""
    tasks: list[asyncio.Task[None]] = [asyncio.create_task(actor.stop()) for actor in actors]
    await asyncio.gather(*tasks)


async def run_actors_forever(actors: list[BaseActor]) -> None:
    """Run actors until interrupted."""
    try:
        await start_multiple_actors(actors)

        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logging.info("Received interrupt signal, shutting down...")
    finally:
        await stop_multiple_actors(actors)
