# app.py
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from api.ik_routes import ik_bp
from api.exec_routes import exec_bp
from core.motion_service import MotionService
from core.drivers import PyBulletDriver, CompositeDriver, SimDriver, CanDriver
import utils.logger  # Import to trigger logging setup

socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    socketio.init_app(app)
    # Initialize Drivers
    pybullet_driver = PyBulletDriver(gui=True, urdf_path="backend/core/models/urdf/arctos_urdf.urdf")
    # Initialize MotionService
    motion_service = MotionService(driver=pybullet_driver)
    motion_service.ws_emit = lambda event, data: socketio.emit(event, data)
    app.config['motion_service'] = motion_service
    motion_service.start()

    # Register blueprints
    app.register_blueprint(ik_bp, url_prefix='/api/ik')
    app.register_blueprint(exec_bp, url_prefix='/api')

    # Example WebSocket channel
    @socketio.on("connect")
    def ws_connect():
        emit("status", {"msg": "Connected to robotic arm backend"})

    return app

if __name__ == "__main__":
    app = create_app()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
