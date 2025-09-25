# app.py
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from api.ik_routes import ik_bp
from api.exec_routes import exec_bp
from api.teleop_routes import teleop_bp
from api.status_routes import status_bp
from api.sim_routes import sim_bp
from api.config_routes import config_bp
from api.ws_routes import init_websocket_events, has_active_connections
from core.drivers import composite_driver
from core.motion_service import MotionService
from core.drivers import PyBulletDriver, CompositeDriver, SimDriver, CanDriver
from core.teleop_controller import TeleopController
from core.input.keyboard_input import KeyboardController
from core.input.xbox_input import XboxController
import utils.logger  # Import to trigger logging setup
import threading
import time

import argparse

socketio = SocketIO(cors_allowed_origins="*")

def run_teleop_loop(teleop_controller):
    """Run the teleoperation control loop."""
    try:
        while True:
            teleop_controller.teleop_step()
            time.sleep(0.02)  # ~50Hz control loop
    except Exception as e:
        print(f"Teleop loop stopped: {e}")
        teleop_controller.stop_all()

def create_app(drivers_list):
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    socketio.init_app(app)
    # Initialize Drivers
    drivers = []
    if 'sim' in drivers_list:
        sim_driver = SimDriver()
        drivers.append(sim_driver)
    if 'pybullet' in drivers_list:
        pybullet_driver = PyBulletDriver(gui=True, urdf_path="backend/models/urdf/arctos_urdf.urdf")
        drivers.append(pybullet_driver)
    if 'can' in drivers_list:
        can_driver = CanDriver()
        drivers.append(can_driver)
    if not drivers:
        # Default to sim if none
        sim_driver = SimDriver()
        drivers.append(sim_driver)
    comp_driver = CompositeDriver(drivers)
    # Initialize MotionService
    motion_service = MotionService(driver=comp_driver, loop_hz=50)
    motion_service.ws_emit = lambda event, data: socketio.emit(event, data)
    motion_service.has_active_connections = has_active_connections
    app.config['motion_service'] = motion_service
    motion_service.start()

    # Register blueprints
    app.register_blueprint(ik_bp, url_prefix='/api/ik')
    app.register_blueprint(exec_bp, url_prefix='/api/execute')
    app.register_blueprint(teleop_bp, url_prefix='/api/teleop')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(sim_bp, url_prefix='/api/sim')
    app.register_blueprint(config_bp, url_prefix='/api/config')

    # Initialize WebSocket event handlers
    init_websocket_events(socketio)

    return app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Arctos Arm Controller")
    parser.add_argument('--drivers', nargs='+', choices=['sim', 'pybullet', 'can'], default=['sim', 'pybullet', 'can'], help="Specify which drivers to use")
    parser.add_argument('--teleop', choices=['keyboard', 'xbox'], help="Enable teleoperation with specified input device")
    args = parser.parse_args()
    app = create_app(args.drivers)
    
    if args.teleop:
        # Start Flask server in a separate thread
        print("Starting Flask server in background...")
        flask_thread = threading.Thread(target=lambda: socketio.run(app, host="0.0.0.0", port=5000, debug=False), daemon=True)
        flask_thread.start()
        
        # Run teleoperation in main thread (required for pygame input handling)
        print(f"Enabling teleoperation with {args.teleop} input...")
        if args.teleop == 'xbox':
            input_controller = XboxController()
        else:
            input_controller = KeyboardController()
        
        # Get the composite driver from the motion service
        comp_driver = app.config['motion_service'].driver
        teleop_controller = TeleopController(input_controller, comp_driver)
        
        print("Teleoperation enabled. Use your input device to control the arm. Press Ctrl+C to exit.")
        try:
            run_teleop_loop(teleop_controller)
        except KeyboardInterrupt:
            print("Shutting down...")
            teleop_controller.stop_all()
            # Stop motion service
            app.config['motion_service'].stop()
    else:
        # Run Flask server normally
        socketio.run(app, host="0.0.0.0", port=5000, debug=True)
