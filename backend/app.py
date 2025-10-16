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
from core.teleop_controller import TeleopController
from core.input.keyboard_input import KeyboardController
from core.input.xbox_input import XboxController
from core.input.finger_input import FingerInput as FingerInputController
from core.input.finger_slider_input import FingerSliderInput
import utils.logger  # Import to trigger logging setup
import threading
import time

import argparse

# Initialize Socket.IO with proper configuration
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='threading',
    engineio_logger=False,
    logger=False,
    ping_timeout=120,
    ping_interval=25
)

def run_teleop_loop(teleop_controller):
    """Run the teleoperation control loop."""
    try:
        while True:
            teleop_controller.teleop_step()
            time.sleep(0.02)  # ~50Hz control loop
    except Exception as e:
        print(f"Teleop loop stopped: {e}")
        raise
    finally:
        teleop_controller.stop_all()

def create_app(drivers_list):
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    socketio.init_app(app)
    logger = logging.getLogger(__name__)
    
    # Initialize Drivers
    drivers = []
    if 'sim' in drivers_list:
        sim_driver = SimDriver()
        drivers.append(sim_driver)
    if 'pybullet' in drivers_list:
        pybullet_driver = PyBulletDriver(gui=True, urdf_path=r"backend\models\urdf\arctos_urdf.urdf")
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

    # Initialize IK Solver
    try:
        ik_solver = AnalyticIKSolver(r"backend\models\urdf\arctos_urdf.urdf")
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
    parser.add_argument('--teleop', choices=['keyboard', 'xbox', 'fingers', 'finger-sliders'], help="Enable teleoperation with specified input device")
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
    
    app = create_app(args.drivers)
    
    if teleop_mode:
        # Start Flask server in a separate thread
        print("Starting Flask server in background...")
        flask_thread = threading.Thread(target=lambda: socketio.run(app, host="0.0.0.0", port=5000, debug=False), daemon=True)
        flask_thread.start()
        
        # Run teleoperation in main thread (required for pygame input handling)
        print(f"Enabling teleoperation with {teleop_mode} input...")
        if teleop_mode == 'xbox':
            input_controller = XboxController()
        elif teleop_mode == 'fingers':
            input_controller = FingerInputController()
        elif teleop_mode == 'finger-sliders':
            input_controller = FingerSliderInput(gesture_update_interval=0.1)  # ~33 Hz
        else:
            input_controller = KeyboardController()
        
        # Get the composite driver and motion service
        comp_driver = app.config['motion_service'].driver
        motion_service = app.config['motion_service']
        teleop_controller = TeleopController(input_controller, comp_driver, motion_service)
        
        print("Teleoperation enabled. Use your input device to control the arm. Press Ctrl+C to exit.")
        try:
            run_teleop_loop(teleop_controller)
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            try:
                teleop_controller.stop_all()
            except Exception:
                pass
            close_method = getattr(input_controller, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    pass
            try:
                app.config['motion_service'].stop()
            except Exception:
                pass
            if flask_thread and flask_thread.is_alive():
                try:
                    socketio.stop()
                except Exception:
                    pass
                flask_thread.join(timeout=5.0)
    else:
        # Run Flask server normally
        print("Starting Flask server without teleoperation...")
        socketio.run(app, host="0.0.0.0", port=5000, debug=False)
