# app.py
from flask import Flask
from flask_socketio import SocketIO, emit
from api.ik_routes import ik_bp
from api.exec_routes import exec_bp

socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret"  # replace in prod

    socketio.init_app(app)

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
