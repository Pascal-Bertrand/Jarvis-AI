from flask_socketio import SocketIO

# Shared SocketIO instance
socketio = SocketIO(cors_allowed_origins="*")

# Optional: If you need to initialize with the app later
# def init_socketio(app):
#     socketio.init_app(app)

def initialize_socketio(app):
    """Attach the Flask app to the SocketIO instance."""
    socketio.init_app(app)
