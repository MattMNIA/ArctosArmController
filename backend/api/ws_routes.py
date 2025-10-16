from flask_socketio import emit, disconnect
from flask import current_app
import logging
import traceback

logger = logging.getLogger(__name__)

# Global connection tracking
active_connections = 0

def init_websocket_events(socketio):
    """Initialize WebSocket event handlers."""

    @socketio.on("connect")
    def ws_connect():
        global active_connections
        active_connections += 1
        logger.info(f"✓ Client connected. Active connections: {active_connections}")
        
        try:
            logger.debug("Attempting to emit status message...")
            emit("status", {"msg": "Connected to robotic arm backend"})
            logger.info("✓ Sent status message")
        except Exception as e:
            logger.error(f"✗ Failed to send status: {e}")
            logger.error(traceback.format_exc())
        
        # Send initial telemetry to the connected client
        try:
            logger.debug("Getting motion_service from app config...")
            motion_service = current_app.config.get('motion_service')
            if motion_service:
                logger.debug("✓ Motion service found")
                if motion_service.driver:
                    logger.debug("✓ Driver found, getting feedback...")
                    feedback = motion_service.driver.get_feedback()
                    if feedback:
                        logger.debug(f"✓ Feedback retrieved: {feedback}")
                        event = {
                            "state": motion_service.current_state,
                            "q": feedback.get("q", []),
                            "encoders": feedback.get("motor_encoders", feedback.get("q", [])),
                            "error": feedback.get("error", []),
                            "limits": feedback.get("limits", []),
                            "gripper_position": motion_service._current_gripper_position
                        }
                        logger.debug(f"Emitting telemetry: {event}")
                        emit("telemetry", event)
                        logger.info("✓ Sent telemetry data")
                    else:
                        logger.warning("✗ Driver returned empty feedback")
                else:
                    logger.warning("✗ Driver not available in motion_service")
            else:
                logger.warning("✗ Motion service not available for initial telemetry")
        except Exception as e:
            logger.error(f"✗ Failed to send initial telemetry on connect: {e}")
            logger.error(traceback.format_exc())

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