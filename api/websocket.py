"""
WebSocket handler for real-time chat communication.

This module provides WebSocket support for the e-commerce support chat widget,
enabling real-time bidirectional communication between the client and the
Actor Mesh system.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

import nats
from fastapi import WebSocket
from models.message import Message, MessagePayload, Route, StandardRoutes
from nats.js import JetStreamContext
from pydantic import BaseModel, ValidationError


class WebSocketMessage(BaseModel):
    """WebSocket message model."""

    type: str  # 'chat', 'ping', 'join', 'leave'
    data: Dict = {}
    timestamp: Optional[str] = None


class ChatWebSocketMessage(BaseModel):
    """Chat-specific WebSocket message."""

    message: str
    customer_email: str
    session_id: Optional[str] = None


class WebSocketManager:
    """
    Manages WebSocket connections and handles real-time communication.

    This class handles multiple WebSocket connections, message routing,
    and integration with the NATS-based Actor Mesh system.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222", timeout: float = 30.0):
        """
        Initialize the WebSocket manager.

        Args:
            nats_url: NATS server URL
            timeout: Response timeout in seconds
        """
        self.nats_url = nats_url
        self.timeout = timeout

        # WebSocket connections
        self.active_connections: Dict[str, WebSocket] = {}
        self.session_connections: Dict[str, str] = {}  # session_id -> connection_id

        # NATS connections
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None

        # Response tracking
        self.pending_requests: Dict[str, str] = {}  # message_id -> connection_id

        # Setup logging
        self.logger = logging.getLogger("websocket.manager")
        self.logger.setLevel(logging.INFO)

    async def startup(self):
        """Initialize NATS connections."""
        try:
            # Connect to NATS
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()

            # Subscribe to response messages
            await self._setup_response_subscription()

            self.logger.info("WebSocket manager started successfully")
        except Exception as e:
            self.logger.error(f"Failed to start WebSocket manager: {str(e)}")
            raise

    async def shutdown(self):
        """Clean up connections on shutdown."""
        try:
            # Close all WebSocket connections
            for connection_id, websocket in list(self.active_connections.items()):
                await self._disconnect(connection_id, websocket, reason="Server shutdown")

            # Close NATS connection
            if self.nc:
                await self.nc.close()

            self.logger.info("WebSocket manager shut down successfully")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")

    async def _setup_response_subscription(self):
        """Set up subscription to response messages."""
        subject = "ecommerce.support.gateway.response"
        await self.nc.subscribe(subject, cb=self._handle_response_message)
        self.logger.info(f"Subscribed to response messages on {subject}")

    async def _handle_response_message(self, msg):
        """Handle incoming response messages from response aggregator."""
        try:
            message_data = msg.data.decode()
            response_data = json.loads(message_data)

            message_id = response_data.get("message_id")
            if message_id and message_id in self.pending_requests:
                connection_id = self.pending_requests.pop(message_id)

                if connection_id in self.active_connections:
                    websocket = self.active_connections[connection_id]

                    # Send response to WebSocket client
                    response_message = WebSocketMessage(
                        type="chat_response",
                        data={
                            "response": response_data.get("response", "Sorry, I couldn't process your request."),
                            "session_id": response_data.get("session_id"),
                            "message_id": message_id,
                            "processing_time": response_data.get("processing_time", 0),
                            "metadata": response_data.get("metadata", {}),
                        },
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )

                    await self._send_to_websocket(websocket, response_message)
                else:
                    self.logger.warning(f"WebSocket connection not found for message: {message_id}")
            else:
                self.logger.warning(f"Received response for unknown message: {message_id}")

        except Exception as e:
            self.logger.error(f"Error handling response message: {str(e)}")

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None) -> str:
        """
        Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            session_id: Optional session ID

        Returns:
            Connection ID
        """
        await websocket.accept()

        connection_id = str(uuid.uuid4())
        self.active_connections[connection_id] = websocket

        if session_id:
            self.session_connections[session_id] = connection_id

        self.logger.info(f"WebSocket connected: {connection_id} (session: {session_id})")

        # Send welcome message
        welcome_message = WebSocketMessage(
            type="connected",
            data={
                "connection_id": connection_id,
                "session_id": session_id,
                "message": "Connected to E-commerce Support Chat",
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await self._send_to_websocket(websocket, welcome_message)

        return connection_id

    async def disconnect(self, connection_id: str):
        """
        Disconnect a WebSocket connection.

        Args:
            connection_id: Connection to disconnect
        """
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            await self._disconnect(connection_id, websocket, reason="Client disconnect")

    async def _disconnect(self, connection_id: str, websocket: WebSocket, reason: str = "Unknown"):
        """Internal disconnect handling."""
        try:
            # Remove from active connections
            self.active_connections.pop(connection_id, None)

            # Remove session mapping
            session_to_remove = None
            for session_id, conn_id in self.session_connections.items():
                if conn_id == connection_id:
                    session_to_remove = session_id
                    break

            if session_to_remove:
                self.session_connections.pop(session_to_remove, None)

            # Clean up pending requests
            messages_to_remove = []
            for message_id, conn_id in self.pending_requests.items():
                if conn_id == connection_id:
                    messages_to_remove.append(message_id)

            for message_id in messages_to_remove:
                self.pending_requests.pop(message_id, None)

            self.logger.info(f"WebSocket disconnected: {connection_id} ({reason})")

        except Exception as e:
            self.logger.error(f"Error during disconnect: {str(e)}")

    async def handle_message(self, websocket: WebSocket, connection_id: str, message_data: str):
        """
        Handle incoming WebSocket message.

        Args:
            websocket: WebSocket connection
            connection_id: Connection ID
            message_data: Raw message data
        """
        try:
            # Parse WebSocket message
            ws_message = WebSocketMessage.model_validate_json(message_data)

            if ws_message.type == "ping":
                # Handle ping/pong
                pong_message = WebSocketMessage(
                    type="pong",
                    data={"timestamp": datetime.now(timezone.utc).isoformat()},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                await self._send_to_websocket(websocket, pong_message)

            elif ws_message.type == "chat":
                # Handle chat message
                await self._handle_chat_message(websocket, connection_id, ws_message.data)

            else:
                self.logger.warning(f"Unknown message type: {ws_message.type}")

        except ValidationError as e:
            self.logger.error(f"Invalid WebSocket message format: {str(e)}")
            error_message = WebSocketMessage(
                type="error",
                data={"error": "Invalid message format", "details": str(e)},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self._send_to_websocket(websocket, error_message)

        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {str(e)}")
            error_message = WebSocketMessage(
                type="error", data={"error": "Internal server error"}, timestamp=datetime.now(timezone.utc).isoformat()
            )
            await self._send_to_websocket(websocket, error_message)

    async def _handle_chat_message(self, websocket: WebSocket, connection_id: str, data: Dict):
        """Handle chat-specific WebSocket messages."""
        try:
            # Validate chat message
            chat_message = ChatWebSocketMessage.model_validate(data)

            session_id = chat_message.session_id or f"ws_session_{connection_id}"
            message_id = str(uuid.uuid4())

            # Create message payload
            payload = MessagePayload(
                customer_message=chat_message.message,
                customer_email=chat_message.customer_email,
            )

            # Create route using standard processing pipeline
            route = Route(steps=StandardRoutes.FULL_PROCESSING_PIPELINE.copy())

            # Create message
            message = Message(
                message_id=message_id,
                session_id=session_id,
                route=route,
                payload=payload,
                metadata={
                    "websocket_request": True,
                    "connection_id": connection_id,
                    "gateway_timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Track pending request
            self.pending_requests[message_id] = connection_id

            # Send message to first actor in pipeline
            first_actor = route.get_current_actor()
            if first_actor:
                subject = f"ecommerce.support.{first_actor}"
                await self._publish_message(subject, message)
                self.logger.info(f"Sent WebSocket message {message_id} to {first_actor}")

                # Send acknowledgment
                ack_message = WebSocketMessage(
                    type="message_sent",
                    data={"message_id": message_id, "session_id": session_id, "status": "processing"},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                await self._send_to_websocket(websocket, ack_message)
            else:
                raise ValueError("No actors in processing pipeline")

        except ValidationError as e:
            self.logger.error(f"Invalid chat message format: {str(e)}")
            error_message = WebSocketMessage(
                type="error",
                data={"error": "Invalid chat message format", "details": str(e)},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self._send_to_websocket(websocket, error_message)

        except Exception as e:
            self.logger.error(f"Error processing chat message: {str(e)}")
            error_message = WebSocketMessage(
                type="error", data={"error": "Failed to process chat message"}, timestamp=datetime.now(timezone.utc).isoformat()
            )
            await self._send_to_websocket(websocket, error_message)

    async def _send_to_websocket(self, websocket: WebSocket, message: WebSocketMessage):
        """Send message to WebSocket client."""
        try:
            message_json = message.model_dump_json()
            await websocket.send_text(message_json)
        except Exception as e:
            self.logger.error(f"Failed to send WebSocket message: {str(e)}")
            raise

    async def _publish_message(self, subject: str, message: Message) -> None:
        """Publish message to NATS subject."""
        try:
            message_json = message.model_dump_json()
            await self.nc.publish(subject, message_json.encode())
            self.logger.debug(f"Published message to {subject}")
        except Exception as e:
            self.logger.error(f"Failed to publish message to {subject}: {str(e)}")
            raise

    async def broadcast_to_session(self, session_id: str, message: WebSocketMessage):
        """
        Broadcast message to all connections in a session.

        Args:
            session_id: Session ID
            message: Message to broadcast
        """
        connection_id = self.session_connections.get(session_id)
        if connection_id and connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            await self._send_to_websocket(websocket, message)

    async def broadcast_to_all(self, message: WebSocketMessage):
        """
        Broadcast message to all active connections.

        Args:
            message: Message to broadcast
        """
        for websocket in self.active_connections.values():
            try:
                await self._send_to_websocket(websocket, message)
            except Exception as e:
                self.logger.error(f"Failed to broadcast to WebSocket: {str(e)}")

    def get_connection_stats(self) -> Dict:
        """Get connection statistics."""
        return {
            "active_connections": len(self.active_connections),
            "active_sessions": len(self.session_connections),
            "pending_requests": len(self.pending_requests),
            "connections": list(self.active_connections.keys()),
        }


# Global WebSocket manager instance
websocket_manager = WebSocketManager()
