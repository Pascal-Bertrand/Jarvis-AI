# import os
# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from flask_socketio import SocketIO, join_room, leave_room
# import jwt # What is this?
# from functools import wraps

# app = Flask(__name__)
# CORS(app, origins=["http://localhost:3000", "https://your-vercel-app.vercel.app"])
# socketio = SocketIO(app, cors_allowed_origins="*")

# # Database connection
# # This establishes a connection to the database using the DATABASE_URL environment variable.
# db = Database(os.getenv('DATABASE_URL'))

# # User agent managers (one per authenticated user)
# # This dictionary stores UserAgentManager instances, keyed by user_id.
# # Each UserAgentManager handles the agents and interactions for a specific authenticated user.
# user_managers = {}

# def verify_token(f):
#     """
#     Decorator function to verify JWT token from the Authorization header.

#     This decorator checks for the presence of a JWT token in the 'Authorization'
#     header of the incoming request. It decodes the token to extract the user ID
#     and attaches it to the `request` object.

#     Args:
#         f: The function to be decorated.

#     Returns:
#         The decorated function, which will first verify the token before executing.
#         Returns a JSON error response and a 401 status code if the token is
#         missing or invalid.
#     """
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         """
#         Inner function that performs the token verification.
#         """
#         token = request.headers.get('Authorization')
#         if not token:
#             return jsonify({'error': 'No token provided'}), 401
        
#         try:
#             user_id = payload.get('userId')
#             # Remove 'Bearer ' prefix if present
#             token = token.replace('Bearer ', '')
#             # Decode the JWT token using the NEXTAUTH_SECRET and HS256 algorithm
#             payload = jwt.decode(token, os.getenv('NEXTAUTH_SECRET'), algorithms=['HS256'])
#             user_id = payload.get('userId') # Extract user ID from the token payload
#             if not user_id:
#                 return jsonify({'error': 'Invalid token'}), 401
            
#             # Attach user_id to the request object for use in the route handler
#             request.user_id = user_id
#             return f(*args, **kwargs)
#         except jwt.InvalidTokenError:
#             # Handle cases where the token is invalid (e.g., expired, malformed)
#             return jsonify({'error': 'Invalid token'}), 401
    
#     return decorated

# @app.route('/api/initialize', methods=['POST'])
# @verify_token
# def initialize_user_agents():
#     """
#     Initialize agents for a user when they first log in or when their session starts.

#     This endpoint is called to set up the necessary UserAgentManager for a given user
#     if one doesn't already exist. It ensures that default agents are initialized for the user.

#     The user must be authenticated via the `verify_token` decorator.

#     Returns:
#         JSON response: {'status': 'initialized'} on successful initialization.
#     """
#     user_id = request.user_id # Get user_id from the request object (set by verify_token)
    
#     # Check if a UserAgentManager already exists for this user
#     if user_id not in user_managers:
#         # If not, create a new UserAgentManager instance
#         user_managers[user_id] = UserAgentManager(user_id, db, socketio)
#         # Initialize default agents for the newly created manager
#         user_managers[user_id].initialize_default_agents()
    
#     return jsonify({'status': 'initialized'})

# @app.route('/api/nodes')
# @verify_token
# def get_user_agents():
#     """
#     Retrieve the agents (nodes) associated with the authenticated user.

#     If the user is not yet initialized (i.e., no UserAgentManager exists for them),
#     this function will first initialize them and their default agents.
#     Then, it fetches and returns the list of agents.

#     The user must be authenticated via the `verify_token` decorator.

#     Returns:
#         JSON response: A list of agent objects.
#     """
#     user_id = request.user_id # Get user_id from the request object
    
#     # Ensure the user's UserAgentManager is initialized
#     if user_id not in user_managers:
#         user_managers[user_id] = UserAgentManager(user_id, db, socketio)
#         user_managers[user_id].initialize_default_agents()
    
#     # Get the agents from the user's UserAgentManager
#     agents = user_managers[user_id].get_agents()
#     return jsonify(agents)

# @app.route('/api/send_message', methods=['POST'])
# @verify_token
# def send_message():
#     """
#     Send a message from one agent (or user) to another agent within the user's context.

#     This endpoint receives a message payload containing the target node ID,
#     the message content, and the sender's ID. It routes the message through
#     the user's UserAgentManager.

#     The user must be authenticated via the `verify_token` decorator.

#     Request JSON payload:
#         {
#             "node_id": "target_agent_id",
#             "message": "The message content",
#             "sender_id": "sending_agent_or_user_id"
#         }

#     Returns:
#         JSON response: The response from the UserAgentManager's send_message method.
#                        Returns an error if the user is not initialized.
#     """
#     user_id = request.user_id # Get user_id from the request object
#     data = request.json # Get the JSON data from the request body
    
#     # Check if the user has an initialized UserAgentManager
#     if user_id not in user_managers:
#         return jsonify({'error': 'User not initialized'}), 400
    
#     # Delegate message sending to the UserAgentManager
#     response = user_managers[user_id].send_message(
#         data.get('node_id'),    # ID of the recipient agent
#         data.get('message'),    # Content of the message
#         data.get('sender_id')   # ID of the sender
#     )
    
#     return jsonify(response)

# @app.route('/api/projects')
# @verify_token
# def get_projects():
#     """
#     Retrieve projects associated with the authenticated user.

#     This endpoint fetches all projects linked to the user_id from the database.
#     An optional 'agent_id' query parameter can be provided, but it is currently unused
#     in the database interaction for fetching projects.

#     The user must be authenticated via the `verify_token` decorator.

#     Query Parameters:
#         agent_id (optional): The ID of an agent (currently not used for filtering projects).

#     Returns:
#         JSON response: A list of project objects.
#     """
#     user_id = request.user_id # Get user_id from the request object
#     agent_id = request.args.get('agent_id') # Get optional agent_id from query parameters
    
#     # Fetch projects for the user from the database
#     projects = db.get_user_projects(user_id)
#     return jsonify(projects)

# @app.route('/api/tasks')
# @verify_token
# def get_tasks():
#     """
#     Retrieve tasks associated with the authenticated user and optionally a specific agent.

#     This endpoint fetches tasks from the database based on the user_id.
#     If an 'agent_id' is provided as a query parameter, tasks are filtered for that agent.

#     The user must be authenticated via the `verify_token` decorator.

#     Query Parameters:
#         agent_id (optional): The ID of an agent to filter tasks by.

#     Returns:
#         JSON response: A list of task objects.
#     """
#     user_id = request.user_id # Get user_id from the request object
#     agent_id = request.args.get('agent_id') # Get optional agent_id from query parameters
    
#     # Fetch tasks for the user, optionally filtered by agent_id
#     tasks = db.get_user_tasks(user_id, agent_id)
#     return jsonify(tasks)

# @app.route('/api/meetings')
# @verify_token
# def get_meetings():
#     """
#     Retrieve meetings associated with the authenticated user.

#     This endpoint fetches all meetings linked to the user_id from the database.
#     An optional 'agent_id' query parameter can be provided, but it is currently unused
#     in the database interaction for fetching meetings.

#     The user must be authenticated via the `verify_token` decorator.

#     Query Parameters:
#         agent_id (optional): The ID of an agent (currently not used for filtering meetings).

#     Returns:
#         JSON response: A list of meeting objects.
#     """
#     user_id = request.user_id # Get user_id from the request object
#     agent_id = request.args.get('agent_id') # Get optional agent_id from query parameters
    
#     # Fetch meetings for the user from the database
#     meetings = db.get_user_meetings(user_id)
#     return jsonify(meetings)

# @socketio.on('join_room')
# def handle_join_room(data):
#     """
#     Handles a SocketIO event for a client joining a room.

#     When a 'join_room' event is received, this function extracts the room name
#     from the event data and uses Flask-SocketIO's `join_room` to add the client
#     to the specified room. This is typically used for targeted communication,
#     e.g., sending updates only to clients interested in a specific user's data.

#     Args:
#         data (dict): A dictionary containing the event data. Expected to have a 'room' key.
#                      Example: {'room': 'user_123_updates'}
#     """
#     room = data.get('room') # Get the room name from the received data
#     if room:
#         join_room(room) # Add the client to the specified SocketIO room

# @socketio.on('leave_room')
# def handle_leave_room(data):
#     """
#     Handles a SocketIO event for a client leaving a room.

#     When a 'leave_room' event is received, this function extracts the room name
#     from the event data and uses Flask-SocketIO's `leave_room` to remove the client
#     from the specified room. This stops the client from receiving messages broadcast
#     to that room.

#     Args:
#         data (dict): A dictionary containing the event data. Expected to have a 'room' key.
#                      Example: {'room': 'user_123_updates'}
#     """
#     room = data.get('room') # Get the room name from the received data
#     if room:
#         leave_room(room) # Remove the client from the specified SocketIO room

# if __name__ == '__main__':
#     # This block executes when the script is run directly (e.g., `python app.py`).
#     # It configures and starts the Flask-SocketIO development server.

#     # Get the port number from the environment variable 'PORT', defaulting to 5001 if not set.
#     port = int(os.environ.get('PORT', 5001))
#     # Run the Flask application with SocketIO support.
#     # host='0.0.0.0' makes the server accessible from any network interface.
#     socketio.run(app, host='0.0.0.0', port=port) 