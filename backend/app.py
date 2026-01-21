import warnings

warnings.filterwarnings(
    "ignore",
    message=r"SymbolDatabase\.GetPrototype\(\).*deprecated",
    category=UserWarning
)
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
from pathlib import Path
from api.ik_routes import ik_bp
from api.exec_routes import exec_bp
from api.teleop_routes import teleop_bp
from api.status_routes import status_bp
from api.sim_routes import sim_bp
from api.config_routes import config_bp
from api.ws_routes import init_websocket_events, has_active_connections
from api.camera_routes import camera_bp
from core.drivers import PyBulletDriver, CompositeDriver, SimDriver, CanDriver
from core.motion_service import MotionService
from core.ik.analytic import AnalyticIKSolver
from core.teleop_manager import TeleopManager, TeleopManagerError
import utils.logger  # Import to trigger logging setup
import threading
import time

import argparse
import sys

# URDF path - use Path for cross-platform compatibility
URDF_PATH = Path(__file__).parent / "models" / "urdf" / "arctos_urdf.urdf"

# Initialize Socket.IO with proper configuration
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='threading',
    engineio_logger=False,
    logger=False,
    ping_timeout=120,
    ping_interval=25
)

def create_app(drivers_list, *, show_vision: bool = None):
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    socketio.init_app(app)
    logger = logging.getLogger(__name__)

    # Initialize IK Solver first (always present)
    ik_solver = None
    gui = 'pybullet' in drivers_list
    try:
        ik_solver = AnalyticIKSolver(str(URDF_PATH), gui=gui)
        app.config['ik_solver'] = ik_solver
        print("IK solver initialized successfully")
    except ImportError as e:
        print(f"Warning: IK solver not available (PyBullet not installed): {e}")
        print("IK functionality will be disabled")
        app.config['ik_solver'] = None
    except Exception as e:
        print(f"Warning: Failed to initialize IK solver: {e}")
        print("IK functionality will be disabled")
        app.config['ik_solver'] = None
    
    # Initialize Drivers
    drivers = []
    if 'sim' in drivers_list:
        sim_driver = SimDriver()
        drivers.append(sim_driver)
    if 'pybullet' in drivers_list:
        shared_client = ik_solver.physics_client if ik_solver else None
        shared_robot_id = ik_solver.robot_id if ik_solver else None
        shared_joint_indices = ik_solver.joint_indices if ik_solver else None
        pybullet_driver = PyBulletDriver(
            gui=True,
            urdf_path=str(URDF_PATH),
            shared_physics_client=shared_client,
            shared_robot_id=shared_robot_id,
            shared_joint_indices=shared_joint_indices
        )
        drivers.append(pybullet_driver)
    if 'can' in drivers_list:
        can_driver = CanDriver()
        drivers.append(can_driver)
    comp_driver = CompositeDriver(drivers)
    # Initialize MotionService
    motion_service = MotionService(driver=comp_driver, loop_hz=50)
    
    # Create a function to emit events from the motion service thread
    def emit_event(event, data):
        """Emit events from motion service thread."""
        try:
            # Emit to all connected clients (namespace='/')
            socketio.emit(event, data, namespace='/')
        except Exception as e:
            # Silent fail - no clients connected or connection error
            logger.debug(f"Failed to emit {event}: {e}")
    
    motion_service.ws_emit = emit_event
    motion_service.has_active_connections = has_active_connections
    app.config['motion_service'] = motion_service
    app.config['teleop_manager'] = TeleopManager(motion_service, show_vision=show_vision)

    # Register blueprints
    app.register_blueprint(ik_bp, url_prefix='/api/ik')
    app.register_blueprint(exec_bp, url_prefix='/api/execute')
    app.register_blueprint(teleop_bp, url_prefix='/api/teleop')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(sim_bp, url_prefix='/api/sim')
    app.register_blueprint(config_bp, url_prefix='/api/config')
    app.register_blueprint(camera_bp, url_prefix='/api/camera')

    # Add a simple health check endpoint
    @app.route('/health', methods=['GET'])
    def health():
        return {'status': 'ok', 'motion_service_running': motion_service.running}

    # Initialize WebSocket event handlers BEFORE starting motion service
    init_websocket_events(socketio)
    
    # NOW start the motion service (after WebSocket handlers are registered)
    motion_service.start()

    return app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Arctos Arm Controller")
    parser.add_argument('--drivers', nargs='+', choices=['sim', 'pybullet', 'can'], default=['can'], help="Specify which drivers to use")
    parser.add_argument('--teleop', choices=['keyboard', 'xbox', 'fingers', 'finger-sliders', 'object-centering'], help="Enable teleoperation with specified input device")
    parser.add_argument('--center-label', default=None, help="Preferred detection label when using object-centering input")
    parser.add_argument('--yolo-model', default=None, help="YOLO model path/name for object centering")
    parser.add_argument('--show-vision', dest='show_vision', action='store_true', default=None, help="Show the camera feed window for vision-based teleop modes")
    parser.add_argument('--no-show-vision', dest='show_vision', action='store_false', help="Hide the camera feed window for vision-based teleop modes")
    parser.add_argument('--invert-horizontal', action='store_true', help="Invert horizontal centering direction")
    parser.add_argument('--invert-vertical', action='store_true', help="Invert vertical centering direction")
    args = parser.parse_args()
    
    # Check if Xbox controller is connected
    xbox_available = False
    try:
        import pygame
        pygame.init()
        pygame.joystick.init()
        xbox_available = pygame.joystick.get_count() > 0
        pygame.quit()
    except ImportError:
        pass
    
    # Determine teleop mode
    teleop_mode = args.teleop
    if teleop_mode is None and xbox_available:
        teleop_mode = 'xbox'
    
    app = create_app(args.drivers, show_vision=args.show_vision)
    
    if teleop_mode:
        # Start Flask server in a separate thread
        print("Starting Flask server in background...")
        flask_thread = threading.Thread(target=lambda: socketio.run(app, host="0.0.0.0", port=5000, debug=False), daemon=True)
        flask_thread.start()

        teleop_manager = app.config['teleop_manager']
        # Build options based on teleop mode
        if teleop_mode == 'object-centering':
            options = {
                "centerLabel": args.center_label,
                "detectorModel": args.yolo_model,
                "displayFeed": args.show_vision,
                "invertHorizontal": args.invert_horizontal,
                "invertVertical": args.invert_vertical,
            }
        elif teleop_mode in ('fingers', 'finger-sliders'):
            options = {
                "showWindow": args.show_vision,
            }
        else:
            options = {}
        # Filter out None values to avoid overriding defaults with nulls
        options = {k: v for k, v in options.items() if v is not None}

        print(f"Enabling teleoperation with {teleop_mode} input...")
        try:
            teleop_manager.start_mode(teleop_mode, options=options)
        except TeleopManagerError as exc:
            print(f"Failed to start teleoperation: {exc}")
            raise SystemExit(1) from exc

        print("Teleoperation enabled. Press Ctrl+C to exit.")

        # Prepare force-exit mechanism
        import os
        shutdown_initiated = threading.Event()

        def force_exit_after_delay():
            # Wait for shutdown to be initiated
            shutdown_initiated.wait()
            time.sleep(3.0)
            print("\nShutdown taking too long, forcing exit...")
            os._exit(0)

        force_exit_thread = threading.Thread(target=force_exit_after_delay, daemon=True)
        force_exit_thread.start()

        # Teleop loop runs in background thread, wait for Ctrl+C
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass  # Fall through to shutdown

        # Signal force-exit thread that shutdown has started
        shutdown_initiated.set()
        print("\nShutting down...")
        try:
            teleop_manager.stop()
            print("Teleop manager stopped")
        except Exception as e:
            print(f"Error stopping teleop manager: {e}")
        try:
            app.config['motion_service'].stop()
            print("Motion service stopped")
        except Exception as e:
            print(f"Error stopping motion service: {e}")
        if flask_thread and flask_thread.is_alive():
            try:
                socketio.stop()
                print("SocketIO stopped")
            except Exception as e:
                print(f"Error stopping SocketIO: {e}")
            flask_thread.join(timeout=2.0)
            print("Flask thread joined")
        print("Shutdown complete")
    else:
        # Run Flask server normally
        print("Starting Flask server without teleoperation...")
        socketio.run(app, host="0.0.0.0", port=5000, debug=False)
