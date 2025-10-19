"""
FastAPI Gateway for the E-commerce Support Agent.

This module provides the HTTP API gateway that converts incoming HTTP requests
to NATS messages and handles response correlation for the Actor Mesh Demo.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import nats
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from models.message import Message, MessagePayload, Route, StandardRoutes
from nats.js import JetStreamContext
from pydantic import BaseModel, Field

from api.websocket import websocket_manager


class ChatRequest(BaseModel):
    """Request model for chat API."""

    message: str = Field(description="Customer message")
    customer_email: str = Field(description="Customer email address")
    session_id: Optional[str] = Field(default=None, description="Session identifier")


class ChatResponse(BaseModel):
    """Response model for chat API."""

    response: str = Field(description="Agent response")
    session_id: str = Field(description="Session identifier")
    message_id: str = Field(description="Message identifier")
    processing_time: float = Field(description="Processing time in seconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    services: Dict[str, str]


class APIGateway:
    """
    FastAPI Gateway that converts HTTP requests to NATS messages.

    Handles request/response correlation and provides REST endpoints
    for the e-commerce support agent system.
    """

    def __init__(self, nats_url: str = "nats://localhost:4222", timeout: float = 30.0):
        """
        Initialize the API Gateway.

        Args:
            nats_url: NATS server URL
            timeout: Response timeout in seconds
        """
        self.nats_url = nats_url
        self.timeout = timeout

        # NATS connections
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None

        # Response tracking
        self.pending_requests: Dict[str, asyncio.Future] = {}

        # Setup logging
        self.logger = logging.getLogger("api.gateway")
        self.logger.setLevel(logging.INFO)

        # Create FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create and configure the FastAPI application."""
        app = FastAPI(
            title="E-commerce Support Agent API",
            description="Actor Mesh Demo API Gateway",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
        )

        # CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Route handlers
        app.post("/api/chat", response_model=ChatResponse)(self.chat_endpoint)
        app.get("/api/health", response_model=HealthResponse)(self.health_endpoint)
        app.get("/")(self.root_endpoint)
        app.get("/widget")(self.widget_endpoint)
        app.websocket("/ws")(self.websocket_endpoint)

        # Mount static files for web directory
        web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        if os.path.exists(web_dir):
            app.mount("/static", StaticFiles(directory=web_dir), name="static")

        # Startup/shutdown events
        app.add_event_handler("startup", self.startup)
        app.add_event_handler("shutdown", self.shutdown)

        return app

    async def startup(self):
        """Initialize connections on startup."""
        try:
            # Connect to NATS
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()

            # Subscribe to response messages
            await self._setup_response_subscription()

            # Start WebSocket manager
            await websocket_manager.startup()

            self.logger.info("API Gateway started successfully")
        except Exception as e:
            self.logger.error(f"Failed to start API Gateway: {str(e)}")
            raise

    async def shutdown(self):
        """Clean up connections on shutdown."""
        try:
            # Shutdown WebSocket manager
            await websocket_manager.shutdown()

            if self.nc:
                await self.nc.close()
            self.logger.info("API Gateway shut down successfully")
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
            import json

            response_data = json.loads(message_data)

            message_id = response_data.get("message_id")
            if message_id and message_id in self.pending_requests:
                future = self.pending_requests.pop(message_id)
                if not future.done():
                    future.set_result(response_data)
            else:
                self.logger.warning(f"Received response for unknown message: {message_id}")

        except Exception as e:
            self.logger.error(f"Error handling response message: {str(e)}")

    async def chat_endpoint(self, request: ChatRequest) -> ChatResponse:
        """
        Handle chat API requests.

        Args:
            request: Chat request with customer message

        Returns:
            Chat response with agent reply
        """
        start_time = datetime.now(timezone.utc)
        session_id = request.session_id or str(uuid.uuid4())
        message_id = str(uuid.uuid4())

        try:
            self.logger.info(f"Processing chat request: {message_id}")

            # Create message payload
            payload = MessagePayload(
                customer_message=request.message,
                customer_email=request.customer_email,
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
                    "api_request": True,
                    "gateway_timestamp": start_time.isoformat(),
                },
            )

            # Set up response future
            response_future = asyncio.Future()
            self.pending_requests[message_id] = response_future

            # Send message to first actor in pipeline
            first_actor = route.get_current_actor()
            if first_actor:
                subject = f"ecommerce.support.{first_actor}"
                await self._publish_message(subject, message)
                self.logger.info(f"Sent message {message_id} to {first_actor}")
            else:
                raise HTTPException(status_code=500, detail="No actors in processing pipeline")

            # Wait for response with timeout
            try:
                response_data = await asyncio.wait_for(response_future, timeout=self.timeout)
            except asyncio.TimeoutError:
                # Clean up pending request
                self.pending_requests.pop(message_id, None)
                raise HTTPException(status_code=504, detail=f"Request timeout after {self.timeout} seconds")

            # Calculate processing time
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Return response
            return ChatResponse(
                response=response_data.get("response", "Sorry, I couldn't process your request."),
                session_id=session_id,
                message_id=message_id,
                processing_time=processing_time,
                metadata=response_data.get("metadata", {}),
            )

        except HTTPException:
            raise
        except Exception as e:
            # Clean up pending request
            self.pending_requests.pop(message_id, None)
            self.logger.error(f"Error processing chat request {message_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def health_endpoint(self) -> HealthResponse:
        """Health check endpoint."""
        try:
            # Check NATS connection
            nats_status = "connected" if self.nc and self.nc.is_connected else "disconnected"

            # Check pending requests
            pending_count = len(self.pending_requests)

            return HealthResponse(
                status="healthy" if nats_status == "connected" else "unhealthy",
                timestamp=datetime.now(timezone.utc).isoformat(),
                services={
                    "nats": nats_status,
                    "pending_requests": str(pending_count),
                    "jetstream": "connected" if self.js else "disconnected",
                },
            )
        except Exception as e:
            self.logger.error(f"Health check error: {str(e)}")
            return HealthResponse(status="error", timestamp=datetime.now(timezone.utc).isoformat(), services={"error": str(e)})

    async def root_endpoint(self):
        """Root endpoint with API information."""
        return {
            "service": "E-commerce Support Agent API",
            "version": "1.0.0",
            "description": "Actor Mesh Demo API Gateway",
            "endpoints": {
                "chat": "/api/chat",
                "health": "/api/health",
                "widget": "/widget",
                "docs": "/docs",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def widget_endpoint(self):
        """Serve the web chat widget."""
        web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        widget_path = os.path.join(web_dir, "widget.html")

        if os.path.exists(widget_path):
            return FileResponse(widget_path)
        else:
            raise HTTPException(status_code=404, detail="Web widget not found")

    async def websocket_endpoint(self, websocket: WebSocket):
        """Handle WebSocket connections for real-time chat."""
        connection_id = None
        try:
            # Accept connection and get connection ID
            session_id = websocket.query_params.get("session_id")
            connection_id = await websocket_manager.connect(websocket, session_id)

            # Handle messages
            while True:
                try:
                    data = await websocket.receive_text()
                    await websocket_manager.handle_message(websocket, connection_id, data)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    self.logger.error(f"Error in WebSocket communication: {str(e)}")
                    break

        except WebSocketDisconnect:
            pass
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {str(e)}")
        finally:
            if connection_id:
                await websocket_manager.disconnect(connection_id)

    async def _publish_message(self, subject: str, message: Message) -> None:
        """Publish message to NATS subject."""
        try:
            message_json = message.model_dump_json()
            await self.nc.publish(subject, message_json.encode())
            self.logger.debug(f"Published message to {subject}")
        except Exception as e:
            self.logger.error(f"Failed to publish message to {subject}: {str(e)}")
            raise


# FastAPI app instance for external use
gateway_instance = APIGateway()
app = gateway_instance.app


if __name__ == "__main__":
    import uvicorn

    # Run the server
    uvicorn.run(
        "api.gateway:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
