import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, join_room, leave_room
import jwt
from functools import wraps
from database import Database
from user_agent_manager import UserAgentManager

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "https://your-vercel-app.vercel.app"])
socketio = SocketIO(app, cors_allowed_origins="*")

# Database connection
db = Database(os.getenv('DATABASE_URL'))

# User agent managers (one per authenticated user)
user_managers = {}

def verify_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        try:
            # Remove 'Bearer ' prefix
            token = token.replace('Bearer ', '')
            payload = jwt.decode(token, os.getenv('NEXTAUTH_SECRET'), algorithms=['HS256'])
            user_id = payload.get('userId')
            if not user_id:
                return jsonify({'error': 'Invalid token'}), 401
            
            request.user_id = user_id
            return f(*args, **kwargs)
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
    
    return decorated

@app.route('/api/initialize', methods=['POST'])
@verify_token
def initialize_user_agents():
    """Initialize agents for a user when they first log in"""
    user_id = request.user_id
    
    if user_id not in user_managers:
        user_managers[user_id] = UserAgentManager(user_id, db, socketio)
        user_managers[user_id].initialize_default_agents()
    
    return jsonify({'status': 'initialized'})

@app.route('/api/nodes')
@verify_token
def get_user_agents():
    user_id = request.user_id
    
    if user_id not in user_managers:
        user_managers[user_id] = UserAgentManager(user_id, db, socketio)
        user_managers[user_id].initialize_default_agents()
    
    agents = user_managers[user_id].get_agents()
    return jsonify(agents)

@app.route('/api/send_message', methods=['POST'])
@verify_token
def send_message():
    user_id = request.user_id
    data = request.json
    
    if user_id not in user_managers:
        return jsonify({'error': 'User not initialized'}), 400
    
    response = user_managers[user_id].send_message(
        data.get('node_id'),
        data.get('message'),
        data.get('sender_id')
    )
    
    return jsonify(response)

@app.route('/api/projects')
@verify_token
def get_projects():
    user_id = request.user_id
    agent_id = request.args.get('agent_id')
    
    projects = db.get_user_projects(user_id)
    return jsonify(projects)

@app.route('/api/tasks')
@verify_token
def get_tasks():
    user_id = request.user_id
    agent_id = request.args.get('agent_id')
    
    tasks = db.get_user_tasks(user_id, agent_id)
    return jsonify(tasks)

@app.route('/api/meetings')
@verify_token
def get_meetings():
    user_id = request.user_id
    agent_id = request.args.get('agent_id')
    
    meetings = db.get_user_meetings(user_id)
    return jsonify(meetings)

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    join_room(room)

@socketio.on('leave_room')
def handle_leave_room(data):
    room = data.get('room')
    leave_room(room)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    socketio.run(app, host='0.0.0.0', port=port) 