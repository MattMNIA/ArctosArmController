# app.py
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from api.ik_routes import ik_bp
from api.exec_routes import exec_bp
from api.teleop_routes import teleop_bp
from api.status_routes import status_bp
from api.sim_routes import sim_bp
from core.drivers import composite_driver
from core.motion_service import MotionService
from core.drivers import PyBulletDriver, CompositeDriver, SimDriver, CanDriver
import utils.logger  # Import to trigger logging setup

import argparse

socketio = SocketIO(cors_allowed_origins="*")

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
    app.config['motion_service'] = motion_service
    motion_service.start()

    # Register blueprints
    app.register_blueprint(ik_bp, url_prefix='/api/ik')
    app.register_blueprint(exec_bp, url_prefix='/api/execute')
    app.register_blueprint(teleop_bp, url_prefix='/api/teleop')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(sim_bp, url_prefix='/api/sim')

    # Example WebSocket channel
    @socketio.on("connect")
    def ws_connect():
        emit("status", {"msg": "Connected to robotic arm backend"})

    return app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Arctos Arm Controller")
    parser.add_argument('--drivers', nargs='+', choices=['sim', 'pybullet', 'can'], default=['sim', 'pybullet', 'can'], help="Specify which drivers to use")
    args = parser.parse_args()
    app = create_app(args.drivers)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
