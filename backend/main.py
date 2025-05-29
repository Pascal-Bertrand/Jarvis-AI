import openai
import os
from typing import Dict, Optional, List
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from flask import Flask, render_template, jsonify, request
import threading
import webbrowser
from flask_cors import CORS
import base64
import tempfile
from config.agents import AGENT_CONFIG
from datetime import datetime
import jwt  # Add JWT for token verification
import json

from secretary.utilities.logging import log_system_message, log_error, log_warning
from network.internal_communication import Intercom

from secretary.communication import Communication
from secretary.brain import Brain, LLMClient
from secretary.scheduler import Scheduler
from secretary.utilities.google import initialize_google_services
from secretary.socketio_ext import socketio

from flask_socketio import join_room, leave_room
from flask import request as flask_request

# Initialize the OpenAI client with your API key
try:
    # Try loading from .env file first
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    # Clean up the API key if it contains newlines or spaces
    if api_key:
        api_key = api_key.replace("\n", "").replace(" ", "").strip()
except ImportError:
    api_key = os.getenv("OPENAI_API_KEY")

# Use a local variable for the API key, LLMNode will use this or its own
openai_api_key = api_key
if not openai_api_key:
    raise ValueError("Please set OPENAI_API_KEY in environment variables or .env file")
# Initialize the global client (can be used if LLMNode doesn't provide its own key)
client = openai.OpenAI(api_key=openai_api_key)


log_system_message("OpenAI client initialized successfully")

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify'  # Allows reading, message modification, but not account management
]

# Google OAuth client credentials - these should be set by the developer, not the end user
GOOGLE_CLIENT_ID = '473172815719-uqsf1bv6rior1ctebkernlnamca3mv3e.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')  # Fallback to empty string if not set

def get_user_id_from_request():
    """
    Extract user ID from the Authorization header.
    Returns the user ID if valid, None otherwise.
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        log_warning("No valid Authorization header found")
        return None
    
    token = auth_header.split(' ')[1]
    
    try:
        # Handle base64-encoded JSON token from frontend
        try:
            import base64
            decoded_bytes = base64.b64decode(token + '==')  # Add padding if needed
            decoded_str = decoded_bytes.decode('utf-8')
            token_data = json.loads(decoded_str)
            user_id = token_data.get('sub') or token_data.get('email')
        except:
            # Fallback to JWT decoding (for future improvements)
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get('sub') or decoded.get('userId') or decoded.get('id') or decoded.get('email')
        
        if user_id:
            log_system_message(f"Extracted user ID: {user_id}")
            return user_id
        else:
            log_warning("No user ID found in token")
            return None
    except Exception as e:
        log_error(f"Error decoding token: {e}")
        return None

def require_auth(f):
    """
    Decorator to require authentication for API endpoints.
    """
    def decorated_function(*args, **kwargs):
        user_id = get_user_id_from_request()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        return f(user_id, *args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

class LLMNode:
    def __init__(self, node_id: str, node_name:str, knowledge: str = "",
                 llm_api_key_override: str = "", llm_params: dict = None, network: Optional[Intercom] = None,
                 user_id: str = None):
        """
        Initialize a new LLMNode instance. This class represents an individual AI agent
        within the network, equipped with its own LLM, knowledge, and communication capabilities.

        Args:
            node_id (str): Unique identifier for this node.
            node_name (str): Human-readable name for this node.
            knowledge (str): Initial knowledge or context for the node. This can be a
                             description of its role, capabilities, or specific data it
                             should be aware of.
            llm_api_key_override (str): Specific OpenAI API key for this node. If empty,
                                      it uses the global `openai_api_key` defined at the
                                      module level.
            llm_params (dict): Dictionary of parameters for the Large Language Model (LLM)
                               such as the model name (e.g., "gpt-4.1"), temperature
                               (controlling randomness), and max_tokens (limiting response length).
                               If None, default parameters are used.
            network (Optional[Intercom]): The Intercom network instance this node belongs to.
                                          This enables communication with other nodes.
        """

        self.node_id = node_id
        self.node_name = node_name
        self.knowledge = knowledge # Note: knowledge is not actively used by Brain/Communication yet
        self.user_id = user_id  # Store user ID for data isolation

        # Determine API key to use for this specific node.
        # If an override is provided, use that; otherwise, fall back to the global API key.
        self.api_key = llm_api_key_override if llm_api_key_override else openai_api_key

        # Initialize the OpenAI client for this node.
        # If the node uses the global API key, it shares the global client instance.
        # Otherwise, a new client is created with its specific API key.
        self.openai_client = client if self.api_key == openai_api_key else openai.OpenAI(api_key=self.api_key)

        # Set LLM parameters. If no specific parameters are provided during initialization,
        # default values are used. These defaults include the model, temperature, and max_tokens.
        self.llm_params = llm_params if llm_params else {
            "model": "gpt-4.1",  # Specifies the LLM model to be used.
            "temperature": 0.1,   # Controls the creativity of the LLM's responses. Lower is more deterministic.
            "max_tokens": 1000    # Maximum number of tokens (words/subwords) the LLM can generate in a single response.
        }

        # Store a reference to the Intercom network this node is part of.
        self.network: Optional[Intercom] = network

        # Initialize Google services (Calendar, Gmail) for this node.
        # Each node gets its own set of service instances, potentially with different authentications.
        self.google_services = initialize_google_services(self.node_id)
        self.calendar_service = self.google_services.get('calendar')  # Google Calendar API service
        self.gmail_service = self.google_services.get('gmail')        # Google Gmail API service

        # Initialize Core Components of the LLMNode:
        
        # LLMClient: Handles direct interactions with the LLM (e.g., sending prompts).
        self.llm_client = LLMClient(self.api_key, self.llm_params)

        # Brain: The central processing unit of the node. It manages tasks, projects,
        #        and uses the LLM for decision-making and response generation.
        #        It is provided with the node's ID, API key, network access, LLM parameters,
        #        and a SocketIO instance for real-time communication.
        self.brain = Brain(self.node_id, self.api_key, self.network, self.llm_params, socketio_instance=socketio)
        self.brain.calendar_service = self.calendar_service # Inject calendar service into the brain
        self.brain.gmail_service = self.gmail_service       # Inject gmail service into the brain

        # Scheduler: Manages time-based events and tasks for the node, such as scheduling
        #            meetings or reminders. It interacts with Google Calendar.
        #            It requires the node's ID, calendar service, network access, the brain,
        #            and a SocketIO instance.
        self.scheduler = Scheduler(node_id=self.node_id, calendar_service=self.calendar_service, network=self.network, brain=self.brain, socketio_instance=socketio)

        # Communication: Handles incoming and outgoing messages for the node. It uses the LLMClient
        #                to process messages and interacts with other components like the Brain and Scheduler.
        self.communication = Communication(self.node_id, self.llm_client, self.network, self.api_key)
        # Inject dependencies into the Communication component:
        self.communication.brain = self.brain            # Allows communication to trigger brain functions
        self.communication.scheduler = self.scheduler     # Allows communication to interact with the scheduler
        self.communication.calendar_service = self.calendar_service # Provides calendar access
        self.communication.gmail_service = self.gmail_service       # Provides Gmail access

    def receive_message(self, message: str, sender_id: str) -> Optional[str]: #TODO delete?
        """
        Processes an incoming message via the Communication component and returns the
        textual response generated by the node. This method acts as an entry point for
        messages directed to this specific LLMNode.

        Args:
            message (str): The content of the message received.
            sender_id (str): The unique identifier of the node or entity that sent the message.

        Returns:
            Optional[str]: The textual response generated by the node's Communication component.
                           Returns None if no response is generated.
        """
        # Delegate message processing to the Communication component.
        return self.communication.receive_message(message, sender_id)


app = Flask(__name__, template_folder='UI')
CORS(app)  # Enable CORS for all routes
# Initialize SocketIO with the Flask app instance
socketio.init_app(app) 

network: Optional[Intercom] = None  # Will be set by the main function

#QESTION: Already have that in app.py, so why again here?
@socketio.on('join_room')
def handle_join_room_event(data):
    """
    Handles a SocketIO event when a client requests to join a specific 'room'.
    Rooms are used to segment SocketIO communication, allowing targeted messages.
    For example, messages for a specific agent can be sent only to clients in that agent's room.

    The client is expected to send data containing a 'room' key with the room name as its value.

    Args:
        data (dict): A dictionary received from the client, expected to contain a 'room' key.
                     Example: {'room': 'agent_X_updates'}
    """
    room = data.get('room') # Extract the room name from the received data.
    if room:
        join_room(room) # Flask-SocketIO function to add the client to the specified room.
        # Log that the client has successfully joined the room, including the client's session ID (sid).
        log_system_message(f"Client {flask_request.sid} joined room {room}")
    else:
        # Log a warning if the client attempted to join a room without providing a room name.
        log_warning(f"Client {flask_request.sid} attempted to join a room without specifying room name.")

#QESTION: Already have sth similar in app.py, so why again here?
@socketio.on('leave_room')
def handle_leave_room_event(data):
    """
    Handles a SocketIO event when a client requests to leave a specific 'room'.
    This allows clients to stop receiving messages broadcast to that room.

    The client is expected to send data containing a 'room' key with the room name as its value.

    Args:
        data (dict): A dictionary received from the client, expected to contain a 'room' key.
                     Example: {'room': 'agent_X_updates'}
    """
    room = data.get('room') # Extract the room name from the received data.
    if room:
        leave_room(room) # Flask-SocketIO function to remove the client from the specified room.
        # Log that the client has successfully left the room.
        log_system_message(f"Client {flask_request.sid} left room {room}")
    else:
        # Log a warning if the client attempted to leave a room without providing a room name.
        log_warning(f"Client {flask_request.sid} attempted to leave a room without specifying room name.")

#Set up the UI
@app.route('/')
def index():
    """
    Serves the main HTML page for the user interface.
    This is typically the entry point for users accessing the web application.

    Returns:
        str: The rendered HTML content of 'index.html'.
    """
    return render_template('index.html') # Renders the template located in the 'UI' folder.

# QUESTION: Already have sth similar in app.py, so why again here?
@app.route('/tasks')
def show_tasks():
    """
    API endpoint to retrieve and display tasks, optionally filtered by an agent ID.
    Tasks can be associated with individual agents (LLMNodes) within the network.
    This endpoint consolidates tasks from the relevant agent(s) and returns them as JSON.

    Query Parameters:
        agent_id (str, optional): If provided, only tasks associated with this agent ID
                                  will be returned. If omitted, tasks from all agents
                                  (or all unassigned tasks, depending on logic) might be returned.

    Returns:
        Response: A Flask JSON response containing a list of tasks or an error message.
                  Each task is represented as a dictionary.
                  Returns 500 error if the network is not initialized.
    """
    global network # Access the global network instance.
    if not network:
        # If the network (Intercom) is not initialized, tasks cannot be retrieved.
        log_error("Attempted to access /tasks endpoint before network initialization.")
        return jsonify({"error": "Network not initialized"}), 500

    agent_id_filter = request.args.get('agent_id') # Get the optional 'agent_id' from query parameters.
    all_tasks = [] # Initialize an empty list to store tasks to be returned.

    # Iterate through all nodes (agents) in the network.
    for node_id_loop, node in network.nodes.items():
        # If an agent_id_filter is provided, and the current node does not match, skip it.
        if agent_id_filter and node_id_loop != agent_id_filter:
            continue
        
        # Check if the node has a 'brain' component and if that brain has a 'tasks' list.
        # This is the primary location to find tasks associated with an agent.
        if hasattr(node, 'brain') and node.brain and hasattr(node.brain, 'tasks') and node.brain.tasks:
            for task in node.brain.tasks: # Iterate over tasks in the node's brain.
                # If no filter is applied, or if the task is assigned to the agent specified by agent_id_filter,
                # add the task to the list. The assigned_to field can be a single ID or a comma-separated list.
                if not agent_id_filter or (hasattr(task, 'assigned_to') and 
                    (task.assigned_to == agent_id_filter or 
                     any(role.strip() == agent_id_filter for role in task.assigned_to.split(',')))):
                    all_tasks.append(task.to_dict()) # Convert task object to dictionary for JSON serialization.
        # Fallback: If tasks are not in node.brain.tasks, check if they are stored directly in network.tasks.
        # This provides an alternative way tasks might be managed, though less agent-specific.
        elif network.tasks: 
             for task in network.tasks: # Iterate over tasks in the global network task list.
                 # Apply the same filtering logic as above.
                 if not agent_id_filter or (hasattr(task, 'assigned_to') and 
                    (task.assigned_to == agent_id_filter or 
                     any(role.strip() == agent_id_filter for role in task.assigned_to.split(',')))):
                    all_tasks.append(task.to_dict())

    return jsonify(all_tasks) # Return the consolidated list of tasks as JSON.

#Show nodes
@app.route('/nodes')
def show_nodes():
    """
    API endpoint to retrieve and display a list of all active nodes (agents) in the network.
    This is useful for UIs or other services that need to know which agents are currently running.

    Returns:
        Response: A Flask JSON response containing a list of nodes or an error message.
                  Each node is represented by its ID and name.
                  Returns 500 error if the network is not initialized.
    """
    global network # Access the global network instance.
    if not network:
        log_error("Attempted to access /nodes endpoint before network initialization.")
        return jsonify({"error": "Network not initialized"}), 500

    nodes_with_names = [] # Initialize an empty list to store node information.
    # Iterate through all registered nodes in the network.
    for node_id, node_obj in network.nodes.items():
        nodes_with_names.append({
            "id": node_obj.node_id,  # The unique identifier of the node.
            "name": node_obj.node_name # The human-readable name of the node.
        })
    return jsonify(nodes_with_names) # Return the list of nodes as JSON.

#Show projects
@app.route('/projects')
def show_projects():
    """
    API endpoint to retrieve and display projects, optionally filtered by an agent ID.
    Projects can be owned by an agent or an agent can be a participant.
    This endpoint consolidates project information from relevant agents and returns it as JSON.

    Query Parameters:
        agent_id (str, optional): If provided, only projects where this agent is an owner
                                  or participant will be returned.

    Returns:
        Response: A Flask JSON response containing a dictionary of projects or an error message.
                  Each project includes details like name, participants, owner, description, status,
                  and creation date. The description may include a formatted plan overview.
                  Returns 500 error if the network is not initialized.
    """
    global network # Access the global network instance.
    if not network:
        log_error("Attempted to access /projects endpoint before network initialization.")
        return jsonify({"error": "Network not initialized"}), 500

    agent_id_filter = request.args.get('agent_id') # Get the optional 'agent_id' from query parameters.
    all_projects = {} # Initialize an empty dictionary to store projects (keyed by project_id).

    # Iterate through all nodes (agents) in the network.
    for node_id_loop, node in network.nodes.items():
        # Check if the node has a 'brain' component and if that brain has a 'projects' dictionary.
        if hasattr(node, 'brain') and node.brain and hasattr(node.brain, 'projects'):
            for project_id, project_data in node.brain.projects.items():
                # Determine if the current agent (node_id_loop) is the owner of the project being processed.
                # Note: The agent_id_filter refers to the agent we are filtering FOR, while node_id_loop
                # is the agent whose brain.projects we are currently iterating through.
                # A project is relevant if the filtering agent is an owner (i.e., project is in its list and it matches filter)
                # or if the filtering agent is listed as a participant.
                
                # The project is owned by `node_id_loop` because we are iterating its `brain.projects`.
                # So, if `agent_id_filter` is set, it must be equal to `node_id_loop` for it to be an "owner" match for the filter.
                is_owner_match_for_filter = (node_id_loop == agent_id_filter) 

                # Check if the agent_id_filter is among the participants of the project.
                is_participant_match_for_filter = agent_id_filter in project_data.get("participants", set())

                # Include the project if no filter is applied, or if the agent_id_filter matches the owner or a participant.
                if not agent_id_filter or is_owner_match_for_filter or is_participant_match_for_filter:
                    if project_id not in all_projects: # Avoid adding duplicate projects if seen from multiple agents.
                        project_plan_steps = project_data.get("plan_steps", [])
                        detailed_description = project_data.get("description", "") # Default to existing description if no plan.

                        # If there are plan steps, format them into a detailed HTML description.
                        if project_plan_steps:
                            detailed_description = "<b>Project Plan Overview:</b>"
                            for i, step in enumerate(project_plan_steps):
                                step_name = step.get("name", f"Step {i+1}")
                                step_desc = step.get("description", "No description")
                                responsible = ", ".join(step.get("responsible_participants", ["N/A"]))
                                detailed_description += f"- <b>Step:</b> {step_name}<br>"
                                detailed_description += f"- <b>Description:</b> {step_desc}<br>"
                                detailed_description += f"- <b>Responsible:</b> {responsible}<br><br>"
                        
                        all_projects[project_id] = {
                            "name": project_data.get("name", project_id), # Project name or ID if name is missing.
                            "participants": list(project_data.get("participants", set())), # List of participant IDs.
                            "owner": node_id_loop, # The ID of the agent whose brain.projects this came from.
                            "description": detailed_description, # Formatted description including plan steps.
                            "status": project_data.get("status", "active"), # Project status (e.g., active, completed).
                            "created_at": project_data.get("created_at", datetime.now().isoformat()) # Creation timestamp.
                        }
        else:
            # Log a warning if a node is encountered that doesn't have the expected brain.projects structure.
            log_warning(f"Node {node_id_loop} does not have a brain or projects attribute for filtering in /projects.")

    return jsonify(all_projects)
    # Chat proposed: jsonify(list(all_projects.values()))

#Show meetings
@app.route('/meetings')
def show_meetings():
    """
    API endpoint to retrieve and display upcoming meetings, optionally filtered by an agent ID.
    Meetings are typically managed by each agent's scheduler component (Google Calendar integration).

    Query Parameters:
        agent_id (str, optional): If provided, only meetings relevant to this agent
                                  (e.g., the agent is an attendee or organizer if the scheduler
                                  is specific to that agent) will be returned.

    Returns:
        Response: A Flask JSON response containing a list of meetings or an error message.
                  Each meeting includes details like title, organizer, and attendees.
                  Returns 500 error if the network is not initialized.
    """
    global network # Access the global network instance.
    if not network:
        log_error("Attempted to access /meetings endpoint before network initialization.")
        return jsonify({"error": "Network not initialized"}), 500

    agent_id_filter = request.args.get('agent_id') # Get the optional 'agent_id' from query parameters.
    all_node_meetings = [] # Initialize an empty list to store meeting information.

    # Iterate through all nodes (agents) in the network.
    for node_id_loop, node in network.nodes.items():
        # If an agent_id_filter is provided, and the current node does not match, skip its meetings.
        # This assumes that each node's scheduler primarily manages meetings for that node.
        if agent_id_filter and node_id_loop != agent_id_filter:
            continue
            
        # Check if the node has a 'scheduler' component and if it has a 'get_upcoming_meetings' method.
        if hasattr(node, 'scheduler') and node.scheduler and hasattr(node.scheduler, 'get_upcoming_meetings'):
            try:
                # Retrieve upcoming meetings from the node's scheduler.
                node_meetings = node.scheduler.get_upcoming_meetings()
                if node_meetings:
                    for meeting in node_meetings:
                        # Ensure organizer information is present and defaults if necessary.
                        # If the meeting is from this node's calendar, this node is often the organizer implicitly.
                        if 'organizer' not in meeting or not meeting['organizer']:
                            meeting['organizer'] = {'email': f'{node_id_loop}@agent.ai', 'self': True}
                        elif 'email' not in meeting['organizer']:
                             meeting['organizer']['email'] = f'{node_id_loop}@agent.ai' # Default email if missing.
                        
                        # Ensure a title is present, using summary or a default if necessary.
                        if 'title' not in meeting or not meeting['title']:
                            meeting['title'] = meeting.get('summary', 'Untitled Meeting')
                        
                        # If filtering by agent_id, perform a secondary check to ensure the agent is an attendee.
                        # This is important if a node's scheduler might return meetings where the node is not an attendee
                        # but is merely aware of them (e.g., shared calendar access).
                        if agent_id_filter: # agent_id_filter is the ID of the agent we are interested in.
                            is_attendee = False
                            if meeting.get('attendees'):
                                for attendee in meeting['attendees']:
                                    # Check if the attendee's email starts with the agent_id_filter (case-insensitive).
                                    # This assumes agent emails are formed like 'agent_id@domain.com'.
                                    if attendee.get('email', '').lower().startswith(agent_id_filter.lower()):
                                        is_attendee = True
                                        break
                            if is_attendee:
                                all_node_meetings.append(meeting)
                        else:
                            # If no agent_id_filter, add all meetings from this node's scheduler.
                            # (The outer loop already handles the case where agent_id_filter is set and node_id_loop matches it).
                            all_node_meetings.append(meeting)
            except Exception as e:
                # Log any errors encountered while fetching meetings for a specific node.
                log_error(f"Error fetching meetings for node {node_id_loop} via /meetings: {str(e)}")
        else:
            # Log a warning if a node doesn't have the expected scheduler structure.
            log_warning(f"Node {node_id_loop} does not have a scheduler with get_upcoming_meetings method for /meetings.")

    return jsonify(all_node_meetings) # Return the consolidated list of meetings as JSON.

#Transcribe audio
@app.route('/transcribe_audio', methods=['POST'])
def transcribe_audio():
    """
    API endpoint to receive audio data, transcribe it using OpenAI Whisper, send the
    transcribed text as a message to a specified agent (LLMNode), and optionally
    return an audio response generated by OpenAI TTS from the agent's textual reply.

    The request body should be JSON and include:
    - node_id (str): The ID of the target agent to process the transcribed message.
    - audio_data (str): Base64 encoded audio data (e.g., from a browser recording).
    - sender_id (str, optional): The ID of the entity sending the message. If not provided,
                                 defaults to `node_id`.

    Returns:
        Response: A Flask JSON response containing:
                  - response (str): The textual response from the agent.
                  - terminal_output (str): (Currently empty) Placeholder for any terminal output.
                  - transcription (str): The transcribed text from the audio.
                  - audio_response (str, optional): Base64 encoded audio of the agent's response.
                  Returns 400 for missing data, 404 if node not found, 500 for processing errors.
    """
    global network, client # Access global network and OpenAI client instances.
    if not network:
        log_error("Attempted to access /transcribe_audio endpoint before network initialization.")
        return jsonify({"error": "Network not initialized"}), 500

    data = request.json # Get JSON data from the request body.
    node_id = data.get('node_id')      # Target agent ID.
    audio_data = data.get('audio_data') # Base64 encoded audio.
    sender_id = data.get('sender_id')   # ID of the message sender.

    # If sender_id is not provided in the request, default to the target node_id.
    # This implies the node is effectively sending a message to itself or acting on its own behalf.
    if not sender_id:
        sender_id = node_id
        log_warning(f"Sender ID not provided in /transcribe_audio request, falling back to target node_id: {node_id}")

    # Validate that essential data (node_id, audio_data) is present.
    if not node_id or not audio_data:
        log_warning(f"Missing node_id or audio_data in /transcribe_audio request. Node ID: {node_id}, Audio Data Present: {bool(audio_data)}")
        return jsonify({"error": "Missing node_id or audio_data"}), 400

    # Check if the specified target node exists in the network.
    if node_id not in network.nodes:
        log_warning(f"Node {node_id} not found in /transcribe_audio request.")
        return jsonify({"error": f"Node {node_id} not found"}), 404

    try:
        # Decode the base64 audio data.
        # Remove the data URL prefix (e.g., "data:audio/webm;base64,") if present.
        if 'base64,' in audio_data:
            audio_data = audio_data.split('base64,')[1]

        audio_bytes = base64.b64decode(audio_data) # Decode from base64 to bytes.

        # Save the audio bytes to a temporary file with an .mp3 extension for Whisper API.
        # `delete=False` is used because the file needs to be opened by name later.
        # It will be manually deleted in the `finally` block of a sub-try or after use.
        temp_file_path = None
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(audio_bytes)

        log_system_message(f"[DEBUG] Audio file for transcription saved to {temp_file_path} with size {len(audio_bytes)} bytes")

        transcript_text = "" # Initialize transcript text.
        # Use OpenAI Whisper API for audio transcription.
        with open(temp_file_path, 'rb') as audio_file_for_transcription:
            transcript_result = client.audio.transcriptions.create(
                model="whisper-1",      # Specifies the Whisper model version.
                file=audio_file_for_transcription, # The audio file object.
                language="en",          # Specifies the language of the audio.
                response_format="text"  # Requests the transcription as plain text.
            )
            if isinstance(transcript_result, str): #Make sure it is a string, not an object
                transcript_text = transcript_result
            # If transcript_result is an object with a .text attribute (older API versions behavior)
            # elif hasattr(transcript_result, 'text'):
            #    transcript_text = transcript_result.text 

        # Clean up the temporary audio file.
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            log_system_message(f"[DEBUG] Temporary audio file {temp_file_path} deleted after transcription.")

        log_system_message(f"[DEBUG] Whisper transcription result: {transcript_text}")

        command_text = transcript_text # The transcribed text is treated as a command/message.

        try:
            # Send the transcribed text as a message to the target node's `receive_message` method.
            # The `sender_id` (which could be the node itself or another entity) is passed along.
            log_system_message(f"Sending transcribed message to node '{node_id}' from sender '{sender_id}': '{command_text}'")
            response_text = network.nodes[node_id].receive_message(command_text, sender_id)
            log_system_message(f"Received response from node '{node_id}': '{response_text}'")

            audio_response_base64 = None # Initialize base64 audio response string.
            if response_text: # If the agent generated a textual response.
                try:
                    # Use OpenAI Text-to-Speech (TTS) API to convert the response to audio.
                    speech_response = client.audio.speech.create(
                        model="tts-1",      # Specifies the TTS model.
                        voice="alloy",      # Specifies the voice to be used.
                        input=response_text # The text to be converted to speech.
                    )

                    # Save the TTS output to a temporary MP3 file.
                    temp_speech_file_path = "temp_speech.mp3"
                    speech_response.write_to_file(temp_speech_file_path)

                    # Read the temporary MP3 file and encode its content to base64.
                    with open(temp_speech_file_path, "rb") as audio_file_for_tts_response:
                        audio_response_base64 = base64.b64encode(audio_file_for_tts_response.read()).decode('utf-8')
                    
                    # Delete the temporary speech file.
                    if os.path.exists(temp_speech_file_path):
                        os.unlink(temp_speech_file_path)
                        log_system_message(f"[DEBUG] Temporary speech file {temp_speech_file_path} deleted.")

                except Exception as e:
                    log_error(f"Error generating or encoding speech for TTS response: {str(e)}")
                    # audio_response_base64 remains None if TTS fails.

            # Return the results, including the agent's text response, transcription, and base64 audio response.
            return jsonify({
                "response": response_text,
                "terminal_output": "", # Placeholder, not currently used.
                "transcription": command_text,
                "audio_response": audio_response_base64
            })

        except Exception as e:
            # Log errors occurring during message processing by the agent.
            log_error(f"Error in /transcribe_audio while node {node_id} processing message: {str(e)}")
            return jsonify({"error": f"Error processing message via agent: {str(e)}"}), 500

    except Exception as e:
        # Log errors occurring during audio decoding, temporary file handling, or Whisper transcription.
        log_error(f"Error decoding/transcribing audio in /transcribe_audio: {str(e)}")
        # Ensure temporary file (if created before error) is cleaned up.
        if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                log_system_message(f"[DEBUG] Temporary audio file {temp_file_path} deleted due to an error in transcription process.")
            except Exception as cleanup_e:
                log_error(f"Error cleaning up temp file {temp_file_path} after an error: {cleanup_e}")
        return jsonify({"error": f"Error processing audio: {str(e)}"}), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    """
    API endpoint to send a textual message directly to a specified agent (LLMNode).
    This is a simpler alternative to `/transcribe_audio` when the input is already text.

    The request body should be JSON and include:
    - node_id (str): The ID of the target agent to process the message.
    - message (str): The textual message content.
    - sender_id (str, optional): The ID of the entity sending the message. If not provided,
                                 defaults to `node_id`.

    Returns:
        Response: A Flask JSON response, typically the output of `send_message_internal`,
                  which includes the agent's response or an error.
                  Returns 400 for missing data, 404 if node not found, 500 for network error.
    """
    global network # Access the global network instance.
    if not network:
        log_error("Attempted to access /send_message endpoint before network initialization.")
        return jsonify({"error": "Network not initialized"}), 500

    data = request.json # Get JSON data from the request body.
    node_id = data.get('node_id')    # Target agent ID.
    message = data.get('message')    # Textual message content.
    sender_id = data.get('sender_id') # ID of the message sender.

    # If sender_id is not provided, default to the target node_id.
    if not sender_id:
        sender_id = node_id
        log_warning(f"Sender ID not provided in /send_message request, falling back to target node_id: {node_id}")

    # Validate that essential data (node_id, message) is present.
    if not node_id or not message:
        log_warning(f"Missing node_id or message in /send_message request. Node ID: {node_id}, Message: '{message}'")
        return jsonify({"error": "Missing node_id or message"}), 400

    # Check if the specified target node exists in the network.
    if node_id not in network.nodes:
        log_warning(f"Node {node_id} not found in /send_message request.")
        return jsonify({"error": f"Node {node_id} not found"}), 404

    # Delegate the actual message sending and response handling to the internal function.
    # This promotes separation of concerns (request parsing vs. core logic).
    return send_message_internal(node_id, message, sender_id)


def send_message_internal(node_id: str, message: str, sender_id: str):
    """
    Internal function to process a textual message sent to a specific agent (LLMNode)
    and return its response. This function encapsulates the core logic of message handling.

    Args:
        node_id (str): The unique identifier of the target LLMNode.
        message (str): The textual message to be sent to the node.
        sender_id (str): The unique identifier of the message sender.

    Returns:
        Response: A Flask JSON response containing:
                  - response (str): The textual response from the agent.
                  - terminal_output (str): (Currently empty) Placeholder for any terminal output.
                  Returns 404 if node not found or network unavailable, 500 for processing errors.
    """
    global network # Access the global network instance.
    if not network or node_id not in network.nodes:
        # This check is somewhat redundant if called from `send_message` which already validates,
        # but good for robustness if `send_message_internal` could be called from elsewhere.
        log_error(f"send_message_internal called for invalid node '{node_id}' or uninitialized network.")
        return jsonify({"error": f"Node {node_id} not found or network unavailable"}), 404

    try:
        # Log the routing of the message for debugging and monitoring purposes.
        log_system_message(f"Routing message to node '{node_id}' from sender '{sender_id}': '{message}'")
        
        # Access the target node from the network and call its `receive_message` method.
        # This method is responsible for the agent's internal processing of the message.
        response_text = network.nodes[node_id].receive_message(message, sender_id)
        log_system_message(f"Received response from node '{node_id}': '{response_text}'")

        # Return the agent's response.
        return jsonify({
            "response": response_text,        # The textual reply from the agent.
            "terminal_output": ""           # Placeholder, not currently used.
        })

    except Exception as e:
        # Log any exceptions that occur during the agent's message processing.
        log_error(f"Error processing message for node {node_id} in send_message_internal: {str(e)}")
        return jsonify({"error": f"Error during agent message processing: {str(e)}"}), 500


def start_flask():
    """
    Starts the Flask-SocketIO web server.

    It first checks for a PORT environment variable, typically provided by hosting
    platforms like Railway. If found, it uses that port and binds to host '0.0.0.0'
    to be accessible externally.

    If no PORT environment variable is set (common in local development), it attempts
    to find an available port in the range 5001-5009. This helps avoid conflicts if
    port 5000 (a common default) is already in use.

    The server is run with `debug=False` for production/general use. 
    `allow_unsafe_werkzeug=True` might be needed for the Werkzeug development server's 
    auto-reloader to work correctly with SocketIO, especially in some development environments.
    """
    # Check for Railway's PORT environment variable first.
    railway_port = os.getenv('PORT')
    if railway_port:
        port = int(railway_port) # Convert the port from string to integer.
        print(f"Using Railway PORT: {port}")
        # Run the SocketIO server on the specified port, accessible from any IP address.
        socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
    else:
        # Fallback for local development: try a range of ports.
        for port in range(5001, 5010):
            try:
                print(f"Attempting to start SocketIO server on port {port}")
                # Add allow_unsafe_werkzeug=True if needed for development auto-reloader with SocketIO
                # Run the SocketIO server. 
                socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
                print(f"SocketIO server started successfully on port {port}")
                break  # Exit the loop if the server starts successfully.
            except OSError as e:
                # Handle cases where the port is already in use.
                if 'Address already in use' in str(e):
                    print(f"Port {port} is in use, trying next port...")
                else:
                    # If a different OS error occurs, log it and stop trying.
                    print(f"An unexpected OS error occurred while starting server: {e}")
                    log_error(f"Flask server OS error on port {port}: {e}")
                    break 
            except Exception as e:
                # Handle any other unexpected errors during server startup.
                print(f"An unexpected error occurred trying to start the server: {e}")
                log_error(f"Flask server startup error on port {port}: {e}")
                break


def open_browser():
    """
    Attempts to automatically open the web browser to the application's UI page.

    It iterates through the same port range (5001-5009) that `start_flask` uses
    for local development. For each port, it tries to establish a socket connection.
    If a connection is successful, it assumes the Flask server is running on that port
    and opens `http://localhost:{port}` in the default web browser.

    This function is typically run in a separate thread so it doesn't block the main
    application startup.
    """
    # Iterate through the expected port range for local development.
    for port in range(5001, 5010):
        try:
            # Attempt to connect to the local server on the current port.
            import socket # Import here to keep it local to this function's scope.
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Set a timeout for the connection attempt (e.g., 1 second) to avoid long hangs.
            sock.settimeout(1) 
            result = sock.connect_ex(('127.0.0.1', port)) # connect_ex returns 0 on success.
            sock.close()
            if result == 0:  # If connection is successful (port is open).
                print(f"Flask server detected on port {port}. Opening browser...")
                webbrowser.open(f'http://localhost:{port}') # Open the URL in the browser.
                break # Stop trying other ports once the server is found and browser is opened.
        except socket.error as e:
            # This will catch connection errors if the server is not yet up on this port.
            # print(f"Socket error on port {port} while checking for server: {e} - Retrying or skipping.")
            pass # Silently continue to the next port or if timeout occurs.
        except Exception as e:
            # Catch any other unexpected errors during the browser opening process.
            # print(f"Unexpected error on port {port} when trying to open browser: {e}")
            log_warning(f"Error attempting to open browser for port {port}: {e}")
            continue # Continue to try the next port.

if __name__ == "__main__":
    """
    Main execution block of the application.
    This script is designed to be run directly to start the multi-agent system.

    It performs the following steps:
    1. Initializes the Intercom network for communication between agents (LLMNodes).
    2. Loads agent configurations from `AGENT_CONFIG` (presumably defined in `config.agents`).
    3. For each agent configuration, creates an `LLMNode` instance with its specific ID,
       name, knowledge, and registers it with the Intercom network.
    4. Starts the Flask-SocketIO web server in a separate daemon thread. This allows the
       main thread to continue or finish while the web server keeps running.
    5. Starts the `open_browser` function in a separate daemon thread to automatically
       open the application's UI in a web browser.
    6. Logs that the main thread has finished, indicating that background services (Flask)
       are now running.
    """
    # 1. Initialize the Intercom network.
    # The log_file parameter specifies where communication logs will be stored.
    network = Intercom(log_file="communication_log.txt")
    log_system_message("Intercom network initialized.")

    # 2. & 3. Load agent configurations and create/register LLMNodes.
    if not AGENT_CONFIG:
        log_warning("AGENT_CONFIG is empty. No LLMNodes will be created.")
    else:
        log_system_message(f"Found {len(AGENT_CONFIG)} agent configurations to load.")

    for agent_config in AGENT_CONFIG:
        try:
            # Create a new LLMNode instance for each configuration.
            # It's provided with its ID, name, knowledge, a reference to the network,
            # and the global OpenAI API key (can be overridden per node if needed).
            node = LLMNode(
                node_id=agent_config["id"],
                node_name=agent_config["name"],
                knowledge=agent_config.get("knowledge", ""), # Use .get for optional keys like knowledge
                network=network,
                llm_api_key_override=openai_api_key # Using the global key for all nodes here
            )
            # Register the newly created node with the Intercom network.
            network.register_node(node.node_id, node)
            log_system_message(f"Created and registered LLMNode: {agent_config['id']} - {agent_config['name']}")
        except KeyError as e:
            log_error(f"Missing key {str(e)} in agent configuration: {agent_config}. Skipping this agent.")
        except Exception as e:
            log_error(f"Error creating or registering node for config {agent_config.get('id', 'UNKNOWN_ID')}: {str(e)}. Skipping this agent.")


    #log_system_message(f"All specified LLMNodes registered. Current nodes in network: {list(network.get_all_nodes().keys()) if network else 'Network not initialized'}")

    # 4. Start the Flask-SocketIO web server in a daemon thread.
    # Daemon threads automatically exit when the main program exits.
    log_system_message("Starting Flask-SocketIO server in a background thread...")
    flask_thread = threading.Thread(target=start_flask) 
    flask_thread.daemon = True # Ensures thread doesn't prevent program termination. TODO: Try out daemon=False and see if socketio.emit() actually sends something to the client
    flask_thread.start()

    # 5. Start the browser-opening utility in a daemon thread.
    # This attempts to open the UI in a browser after the server has likely started.
    log_system_message("Attempting to open browser in a background thread...")
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    # The main thread would typically block here if flask_thread.join() was called.
    # By not calling join() on flask_thread (or calling it only if it should block),
    # the main thread can finish, and the Flask server (a daemon thread) will continue running
    # as long as the Python process is alive.
    # If flask_thread.join() were called, it would wait for start_flask to complete, which it doesn't
    # because socketio.run() is a blocking call that runs indefinitely.
    # For a script that just starts background services, letting the main thread finish is fine.
    log_system_message("Main thread initialization complete. Flask server and browser opener are running in background threads.")


# --- Add CV Upload Route ---
# @app.route('/upload_cv', methods=['POST'])
# def upload_cv_route():
#     if 'cv_file' not in request.files:
#         return jsonify({"error": "No file part"}), 400

#     file = request.files['cv_file']
#     if file.filename == '':
#         return jsonify({"error": "No selected file"}), 400

#     # Ensure the filename ends with .pdf (case-insensitive)
#     if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() == 'pdf':
#         temp_file_path = None  # Initialize path variable
#         try:
#             # Create a temporary file to store the PDF
#             with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
#                 file.save(temp_pdf.name)
#                 temp_file_path = temp_pdf.name

#             print(f"[CV Parser] Temporary file saved at: {temp_file_path}")

#             # Return the extracted data successfully
#             print("[CV Parser] Parsing successful.")
#             return jsonify({
#                 'success': True,
#                 #    'summary': cv_data # Contains name, email, phone, education, work_experience, skills
#             }), 200

#         except Exception as e:
#             # Log the error for debugging
#             print(f"[CV Parser] Error processing CV: {str(e)}")
#             # Return a generic error message to the client
#             return jsonify({'error': f"An unexpected error occurred while processing the CV."}), 500
#         finally:
#             # --- Ensure temporary file cleanup ---
#             if temp_file_path and os.path.exists(temp_file_path):
#                 try:
#                     os.remove(temp_file_path)
#                     print(f"[CV Parser] Temporary file deleted: {temp_file_path}")
#                 except Exception as cleanup_e:
#                     # Log cleanup error but don't necessarily fail the request
#                     print(f"[CV Parser] Error deleting temp file during cleanup: {cleanup_e}")
#             # --- End cleanup ---

#     else:
#         # File is not a PDF or has no extension
#         return jsonify({"error": "Invalid file type. Please upload a PDF file."}), 400
# --- End CV Upload Route ---