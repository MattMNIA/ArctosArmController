from flask_socketio import emit
import logging

logger = logging.getLogger(__name__)

# Global connection tracking
active_connections = 0

def init_websocket_events(socketio):
    """Initialize WebSocket event handlers."""

    @socketio.on("connect")
    def ws_connect():
        global active_connections
        active_connections += 1
        logger.info(f"Client connected. Active connections: {active_connections}")
        emit("status", {"msg": "Connected to robotic arm backend"})

    @socketio.on("disconnect")
    def ws_disconnect():
        global active_connections
        active_connections -= 1
        logger.info(f"Client disconnected. Active connections: {active_connections}")

def get_active_connection_count():
    """Get the current number of active websocket connections."""
    return active_connections

def has_active_connections():
    """Check if there are any active websocket connections."""
    return active_connections > 0