"""
Test suite for Phase 6 web interface functionality.

This module tests the web chat widget integration, WebSocket functionality,
and the complete web-based customer interaction flow.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.gateway import APIGateway
from api.websocket import WebSocketManager, WebSocketMessage
from fastapi.testclient import TestClient


class TestWebWidget:
    """Test web widget functionality."""

    @pytest.fixture
    def api_gateway(self):
        """Create API gateway instance for testing."""
        gateway = APIGateway(nats_url="nats://localhost:4222", timeout=5.0)
        return gateway

    @pytest.fixture
    def test_client(self, api_gateway):
        """Create test client."""
        return TestClient(api_gateway.app)

    def test_widget_endpoint_serves_html(self, test_client):
        """Test that widget endpoint serves HTML file."""
        response = test_client.get("/widget")

        # Should return HTML content
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Should contain expected HTML elements
        content = response.text
        assert "<!DOCTYPE html>" in content
        assert "E-commerce Support Chat" in content
        assert "chat-container" in content
        assert "ChatWidget" in content

    def test_chat_widget_enhanced_serves_html(self, test_client):
        """Test that enhanced chat widget serves HTML file."""
        response = test_client.get("/static/chat.html")

        # Should return HTML content or 404 if static files not mounted
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            assert "text/html" in response.headers["content-type"]
            content = response.text
            assert "WebSocketChatWidget" in content or "ChatWidget" in content

    def test_root_endpoint_includes_widget(self, test_client):
        """Test that root endpoint includes widget in available endpoints."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "endpoints" in data
        assert "widget" in data["endpoints"]
        assert data["endpoints"]["widget"] == "/widget"

    @patch("api.gateway.os.path.exists")
    def test_widget_endpoint_not_found(self, mock_exists, test_client):
        """Test widget endpoint when file doesn't exist."""
        mock_exists.return_value = False

        response = test_client.get("/widget")
        assert response.status_code == 404
        assert "Web widget not found" in response.json()["detail"]


class TestWebSocketManager:
    """Test WebSocket manager functionality."""

    @pytest.fixture
    async def ws_manager(self):
        """Create WebSocket manager for testing."""
        manager = WebSocketManager(nats_url="nats://localhost:4222", timeout=5.0)

        # Mock NATS connections
        manager.nc = AsyncMock()
        manager.js = AsyncMock()

        return manager

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket connection."""
        websocket = AsyncMock()
        websocket.accept = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.receive_text = AsyncMock()
        return websocket

    @pytest.mark.asyncio
    async def test_websocket_connect(self, ws_manager, mock_websocket):
        """Test WebSocket connection establishment."""
        session_id = "test_session_123"

        connection_id = await ws_manager.connect(mock_websocket, session_id)

        # Should accept connection
        mock_websocket.accept.assert_called_once()

        # Should generate connection ID
        assert connection_id is not None
        assert len(connection_id) > 0

        # Should track connection
        assert connection_id in ws_manager.active_connections
        assert ws_manager.active_connections[connection_id] == mock_websocket

        # Should map session
        assert session_id in ws_manager.session_connections
        assert ws_manager.session_connections[session_id] == connection_id

        # Should send welcome message
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "connected"
        assert sent_message["data"]["connection_id"] == connection_id
        assert sent_message["data"]["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_websocket_disconnect(self, ws_manager, mock_websocket):
        """Test WebSocket disconnection cleanup."""
        session_id = "test_session_123"

        # Connect first
        connection_id = await ws_manager.connect(mock_websocket, session_id)

        # Add a pending request
        ws_manager.pending_requests["test_message"] = connection_id

        # Disconnect
        await ws_manager.disconnect(connection_id)

        # Should clean up connections
        assert connection_id not in ws_manager.active_connections
        assert session_id not in ws_manager.session_connections

        # Should clean up pending requests
        assert "test_message" not in ws_manager.pending_requests

    @pytest.mark.asyncio
    async def test_handle_ping_message(self, ws_manager, mock_websocket):
        """Test handling ping messages."""
        connection_id = await ws_manager.connect(mock_websocket, "test_session")

        # Reset mock to clear welcome message
        mock_websocket.send_text.reset_mock()

        # Send ping message
        ping_message = json.dumps({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})

        await ws_manager.handle_message(mock_websocket, connection_id, ping_message)

        # Should send pong response
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "pong"
        assert "timestamp" in sent_message["data"]

    @pytest.mark.asyncio
    async def test_handle_chat_message(self, ws_manager, mock_websocket):
        """Test handling chat messages."""
        connection_id = await ws_manager.connect(mock_websocket, "test_session")

        # Reset mock to clear welcome message
        mock_websocket.send_text.reset_mock()

        # Mock NATS publish
        ws_manager.nc.publish = AsyncMock()

        # Send chat message
        chat_message = json.dumps(
            {
                "type": "chat",
                "data": {
                    "message": "I need help with my order",
                    "customer_email": "test@example.com",
                    "session_id": "test_session",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        await ws_manager.handle_message(mock_websocket, connection_id, chat_message)

        # Should publish to NATS
        ws_manager.nc.publish.assert_called_once()

        # Should send acknowledgment
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "message_sent"
        assert "message_id" in sent_message["data"]
        assert sent_message["data"]["status"] == "processing"

    @pytest.mark.asyncio
    async def test_handle_invalid_message(self, ws_manager, mock_websocket):
        """Test handling invalid messages."""
        connection_id = await ws_manager.connect(mock_websocket, "test_session")

        # Reset mock to clear welcome message
        mock_websocket.send_text.reset_mock()

        # Send invalid JSON
        invalid_message = "invalid json {"

        await ws_manager.handle_message(mock_websocket, connection_id, invalid_message)

        # Should send error response
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "error"
        assert "Invalid message format" in sent_message["data"]["error"]

    @pytest.mark.asyncio
    async def test_response_message_handling(self, ws_manager, mock_websocket):
        """Test handling response messages from actors."""
        connection_id = await ws_manager.connect(mock_websocket, "test_session")
        message_id = "test_message_123"

        # Track pending request
        ws_manager.pending_requests[message_id] = connection_id

        # Reset mock to clear welcome message
        mock_websocket.send_text.reset_mock()

        # Create mock NATS message
        mock_nats_msg = MagicMock()
        response_data = {
            "message_id": message_id,
            "response": "Thank you for contacting support. How can I help you today?",
            "session_id": "test_session",
            "processing_time": 2.5,
            "metadata": {"sentiment": "neutral"},
        }
        mock_nats_msg.data.decode.return_value = json.dumps(response_data)

        # Handle response
        await ws_manager._handle_response_message(mock_nats_msg)

        # Should send response to WebSocket
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "chat_response"
        assert sent_message["data"]["response"] == response_data["response"]
        assert sent_message["data"]["message_id"] == message_id
        assert sent_message["data"]["processing_time"] == 2.5

        # Should remove pending request
        assert message_id not in ws_manager.pending_requests

    @pytest.mark.asyncio
    async def test_broadcast_to_session(self, ws_manager, mock_websocket):
        """Test broadcasting messages to specific session."""
        session_id = "test_session_123"
        connection_id = await ws_manager.connect(mock_websocket, session_id)

        # Reset mock to clear welcome message
        mock_websocket.send_text.reset_mock()

        # Broadcast message
        broadcast_message = WebSocketMessage(
            type="broadcast",
            data={"message": "System maintenance in 5 minutes"},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await ws_manager.broadcast_to_session(session_id, broadcast_message)

        # Should send to session WebSocket
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["type"] == "broadcast"
        assert "System maintenance" in sent_message["data"]["message"]

    def test_connection_stats(self, ws_manager):
        """Test connection statistics."""
        # Initially empty
        stats = ws_manager.get_connection_stats()
        assert stats["active_connections"] == 0
        assert stats["active_sessions"] == 0
        assert stats["pending_requests"] == 0
        assert stats["connections"] == []

    @pytest.mark.asyncio
    async def test_websocket_manager_startup_shutdown(self):
        """Test WebSocket manager startup and shutdown."""
        manager = WebSocketManager(nats_url="nats://localhost:4222")

        # Mock NATS
        with patch("nats.connect") as mock_connect:
            mock_nc = AsyncMock()
            mock_js = AsyncMock()
            mock_nc.jetstream.return_value = mock_js
            mock_connect.return_value = mock_nc

            # Test startup
            await manager.startup()

            assert manager.nc == mock_nc
            assert manager.js == mock_js
            mock_nc.subscribe.assert_called_once()

            # Test shutdown
            await manager.shutdown()
            mock_nc.close.assert_called_once()


class TestWebSocketIntegration:
    """Test WebSocket integration with API Gateway."""

    @pytest.fixture
    def api_gateway(self):
        """Create API gateway with WebSocket support."""
        gateway = APIGateway(nats_url="nats://localhost:4222", timeout=5.0)
        return gateway

    @pytest.mark.asyncio
    async def test_websocket_endpoint_integration(self, api_gateway):
        """Test WebSocket endpoint integration."""
        # Mock WebSocket manager
        with patch("api.gateway.websocket_manager") as mock_ws_manager:
            mock_ws_manager.connect = AsyncMock(return_value="test_connection_id")
            mock_ws_manager.disconnect = AsyncMock()
            mock_ws_manager.handle_message = AsyncMock()

            # Mock WebSocket
            mock_websocket = AsyncMock()
            mock_websocket.query_params = {"session_id": "test_session"}
            mock_websocket.receive_text = AsyncMock()
            mock_websocket.receive_text.side_effect = ["test message", Exception("WebSocket disconnect")]

            # Test WebSocket endpoint
            try:
                await api_gateway.websocket_endpoint(mock_websocket)
            except Exception:
                pass  # Expected due to mocked disconnect

            # Should connect and handle message
            mock_ws_manager.connect.assert_called_once_with(mock_websocket, "test_session")
            mock_ws_manager.handle_message.assert_called_once_with(mock_websocket, "test_connection_id", "test message")
            mock_ws_manager.disconnect.assert_called_once_with("test_connection_id")


class TestWebInterfaceE2E:
    """End-to-end tests for web interface."""

    @pytest.fixture
    def api_gateway(self):
        """Create API gateway for E2E testing."""
        gateway = APIGateway(nats_url="nats://localhost:4222", timeout=5.0)
        # Mock NATS for testing
        gateway.nc = AsyncMock()
        gateway.js = AsyncMock()
        return gateway

    @pytest.fixture
    def test_client(self, api_gateway):
        """Create test client for E2E testing."""
        return TestClient(api_gateway.app)

    def test_complete_web_interface_flow(self, test_client):
        """Test complete web interface flow."""
        # 1. Access widget
        response = test_client.get("/widget")
        assert response.status_code == 200
        assert "E-commerce Support Chat" in response.text

        # 2. Check API endpoints are available
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "widget" in data["endpoints"]

        # 3. Health check should work
        response = test_client.get("/api/health")
        assert response.status_code == 200
        health_data = response.json()
        assert "status" in health_data
        assert "services" in health_data

    def test_widget_accessibility_features(self, test_client):
        """Test widget accessibility features."""
        response = test_client.get("/widget")
        assert response.status_code == 200

        content = response.text

        # Should have proper HTML structure
        assert 'lang="en"' in content
        assert '<meta charset="UTF-8">' in content
        assert 'name="viewport"' in content

        # Should have accessible form elements
        assert 'type="email"' in content
        assert "placeholder=" in content
        assert "required" in content

    def test_widget_responsive_design(self, test_client):
        """Test widget responsive design elements."""
        response = test_client.get("/widget")
        assert response.status_code == 200

        content = response.text

        # Should have responsive CSS
        assert "@media (max-width: 768px)" in content
        assert "flex-direction: column" in content
        assert "width: 100%" in content

    def test_widget_javascript_functionality(self, test_client):
        """Test widget JavaScript functionality."""
        response = test_client.get("/widget")
        assert response.status_code == 200

        content = response.text

        # Should have main chat widget class
        assert "class ChatWidget" in content

        # Should have key methods
        assert "sendMessage" in content
        assert "addMessage" in content
        assert "connectWebSocket" in content or "checkConnection" in content

        # Should handle WebSocket or HTTP communication
        assert "WebSocket" in content or "fetch(" in content

    def test_websocket_chat_widget_enhanced(self, test_client):
        """Test enhanced WebSocket chat widget."""
        response = test_client.get("/static/chat.html")

        # Should serve enhanced widget or return 404 if not available
        if response.status_code == 200:
            content = response.text

            # Should have WebSocket functionality
            assert "WebSocketChatWidget" in content
            assert "connectWebSocket" in content
            assert "onWebSocketMessage" in content

            # Should have real-time features
            assert "typing-indicator" in content
            assert "connection-status" in content
            assert "heartbeat" in content or "ping" in content


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
