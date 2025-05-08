import openai
import json
from typing import Dict, Optional, List
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_from_directory
import threading
import webbrowser
from flask_cors import CORS
import base64
import tempfile
import re
from config.agents import AGENT_CONFIG

# --- Import Logging ---
from secretary.utilities.logging import log_user_message, log_agent_message, log_system_message, log_network_message, log_error, log_warning, log_api_request, log_api_response


# --- Import Network Components ---
from network.internal_communication import Intercom
from network.tasks import Task


# --- Import Secretary Components (needed for LLMNode) ---
from secretary.communication import Communication
from secretary.brain import Brain, LLMClient
from secretary.scheduler import Scheduler
from secretary.utilities.google import initialize_google_services
from secretary.socketio_ext import socketio # Import shared socketio instance

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

# Add these constants at the top level
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify'  # Allows reading, message modification, but not account management
]

# Google OAuth client credentials - these should be set by the developer, not the end user
GOOGLE_CLIENT_ID = '473172815719-uqsf1bv6rior1ctebkernlnamca3mv3e.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')  # Fallback to empty string if not set

# Path to store user tokens - each user gets their own token file
TOKEN_FILE_DIR = os.path.join(os.path.expanduser('~'), '.agentai', 'tokens')
if not os.path.exists(TOKEN_FILE_DIR):
    os.makedirs(TOKEN_FILE_DIR, exist_ok=True)


def get_token_file_path(user_id):
    """Get the token file path for a specific user"""
    return os.path.join(TOKEN_FILE_DIR, f'token_{user_id}.pickle')


class LLMNode:
    def __init__(self, node_id: str, knowledge: str = "",
                 llm_api_key_override: str = "", llm_params: dict = None, network: Optional[Intercom] = None):
        """
        Initialize a new LLMNode instance.

        Args:
            node_id (str): Unique identifier for this node.
            knowledge (str): Initial knowledge or context for the node.
            llm_api_key_override (str): Specific API key for this node. If empty, uses the global `openai_api_key`.
            llm_params (dict): Dictionary of LLM parameters such as model, temperature, and max_tokens.
            network (Intercom): The network instance this node belongs to.
        """

        self.node_id = node_id
        self.knowledge = knowledge # Note: knowledge is not actively used by Brain/Communication yet

        # Determine API key to use
        self.api_key = llm_api_key_override if llm_api_key_override else openai_api_key

        # Use the global client if using the global key, otherwise create a new one
        self.openai_client = client if self.api_key == openai_api_key else openai.OpenAI(api_key=self.api_key)

        # Set LLM parameters with default values if none are provided
        self.llm_params = llm_params if llm_params else {
            "model": "gpt-4.1", # Consider making default model dynamic or configurable
            "temperature": 0.1,
            "max_tokens": 1000
        }

        # Initialize an empty conversation history list (managed by Communication)
        # self.conversation_history = [] # Remove, handled by Communication

        # Dictionary to store project information (managed by Brain)
        self.projects = {} # Remove, handled by Brain

        # Local calendar list (potentially redundant if Scheduler manages all calendar state)
        # self.calendar = [] # Remove, handled by Scheduler/Google Calendar

        # Network reference (passed in)
        self.network: Optional[Intercom] = network

        # Initialize Google services (Calendar, Gmail)
        self.google_services = initialize_google_services(self.node_id)
        self.calendar_service = self.google_services.get('calendar')
        self.gmail_service = self.google_services.get('gmail')

        # Initialize Core Components
        self.llm_client = LLMClient(self.api_key, self.llm_params)
        # Pass network, llm_params, and the IMPORTED socketio instance to Brain
        self.brain = Brain(self.node_id, self.api_key, self.network, self.llm_params, socketio_instance=socketio)
        self.brain.calendar_service = self.calendar_service # Inject calendar service
        self.brain.gmail_service = self.gmail_service       # Inject gmail service

        # Initialize Scheduler and inject calendar service and socketio
        self.scheduler = Scheduler(node_id=self.node_id, calendar_service=self.calendar_service, network=self.network, brain=self.brain, socketio_instance=socketio)

        # Initialize Communication and inject dependencies
        self.communication = Communication(self.node_id, self.llm_client, self.network, self.api_key)
        # Inject dependencies into Communication
        self.communication.brain = self.brain           
        self.communication.scheduler = self.scheduler    
        self.communication.calendar_service = self.calendar_service
        self.communication.gmail_service = self.gmail_service      


    def receive_message(self, message: str, sender_id: str) -> Optional[str]:
        """Processes message via Communication and returns the textual response."""
        # Delegate to communication module, which now returns the response
        return self.communication.receive_message(message, sender_id)

    # Remove methods that are now handled by Brain/Communication via receive_message
    # def plan_project(self, project_id: str, objective: str):
    #     self.brain.plan_project(project_id, objective)
    #
    # def generate_tasks_from_plan(self, project_id: str, steps: list, participants: list):
    #     self.brain.generate_tasks_from_plan(project_id, steps, participants)
    #
    # def list_tasks(self):
    #     return self.brain.list_tasks()


# Remove the local Network class definition
# class Network(Intercom):
#     def __init__(self, log_file: Optional[str] = None):
#         super().__init__(log_file)


# Modify the Flask app initialization
app = Flask(__name__, template_folder='UI')
CORS(app)  # Enable CORS for all routes
# Initialize SocketIO with the Flask app instance
socketio.init_app(app) 

network: Optional[Intercom] = None  # Will be set by the main function


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/tasks')
def show_tasks():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500

    agent_id_filter = request.args.get('agent_id')
    all_tasks = []

    for node_id_loop, node in network.nodes.items():
        # If filtering, only process tasks for the specified agent (node)
        if agent_id_filter and node_id_loop != agent_id_filter:
            continue
        
        # Assuming tasks are stored in network.tasks and can be filtered by assigned_to
        # Or, if tasks are within each node's brain:
        if hasattr(node, 'brain') and node.brain and hasattr(node.brain, 'tasks') and node.brain.tasks:
            for task in node.brain.tasks: # Iterate over tasks in the node's brain
                # If not filtering OR if task is assigned to the agent_id_filter
                if not agent_id_filter or (hasattr(task, 'assigned_to') and task.assigned_to == agent_id_filter):
                    all_tasks.append(task.to_dict())
        elif network.tasks: # Fallback to network.tasks if node.brain.tasks isn't the source
             for task in network.tasks:
                 if not agent_id_filter or (hasattr(task, 'assigned_to') and task.assigned_to == agent_id_filter):
                    all_tasks.append(task.to_dict())

    return jsonify(all_tasks)


@app.route('/nodes')
def show_nodes():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500

    # Use the method from People/Intercom if preferred, otherwise this is fine
    nodes = network.get_all_nodes() # Use Intercom's method
    # nodes = list(network.nodes.keys())
    return jsonify(nodes)


@app.route('/projects')
def show_projects():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500

    agent_id_filter = request.args.get('agent_id')
    all_projects = {}

    for node_id_loop, node in network.nodes.items():
        # If filtering by agent, only process projects for that agent
        # A project is relevant if the agent is the owner or a participant
        if hasattr(node, 'brain') and node.brain and hasattr(node.brain, 'projects'):
            for project_id, project_data in node.brain.projects.items():
                is_owner = (node_id_loop == agent_id_filter)
                is_participant = agent_id_filter in project_data.get("participants", set())

                if not agent_id_filter or is_owner or is_participant:
                    if project_id not in all_projects: # Avoid duplicates if multiple agents share a project view
                        all_projects[project_id] = {
                            "name": project_data.get("name", project_id),
                            "participants": list(project_data.get("participants", set())),
                            "owner": node_id_loop # The node that owns/manages this project entry
                        }
        else:
            log_warning(f"Node {node_id_loop} does not have a brain or projects attribute for filtering.")

    return jsonify(all_projects)


@app.route('/meetings')
def show_meetings():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500

    agent_id_filter = request.args.get('agent_id')
    all_node_meetings = []

    for node_id_loop, node in network.nodes.items():
        # If filtering by agent_id, only fetch meetings for that specific agent's scheduler
        if agent_id_filter and node_id_loop != agent_id_filter:
            continue
            
        if hasattr(node, 'scheduler') and node.scheduler and hasattr(node.scheduler, 'get_upcoming_meetings'):
            try:
                node_meetings = node.scheduler.get_upcoming_meetings()
                if node_meetings:
                    for meeting in node_meetings:
                        # Ensure organizer info is present
                        if 'organizer' not in meeting or not meeting['organizer']:
                            meeting['organizer'] = {'email': f'{node_id_loop}@agent.ai', 'self': True}
                        elif 'email' not in meeting['organizer']:
                             meeting['organizer']['email'] = f'{node_id_loop}@agent.ai'
                        
                        # Further filter: include if the agent_id_filter is an attendee
                        # This re-iterates the frontend logic on the backend for robustness
                        if agent_id_filter:
                            is_attendee = False
                            if meeting.get('attendees'):
                                for attendee in meeting['attendees']:
                                    if attendee.get('email', '').lower().startswith(agent_id_filter.lower()):
                                        is_attendee = True
                                        break
                            if is_attendee:
                                all_node_meetings.append(meeting)
                        else:
                            # No filter, add all meetings from this node (though outer loop already filters by node if agent_id_filter is set)
                            all_node_meetings.append(meeting)
            except Exception as e:
                log_error(f"Error fetching meetings for node {node_id_loop}: {str(e)}")
        else:
            log_warning(f"Node {node_id_loop} does not have a scheduler with get_upcoming_meetings method.")
    
    # Optional: sort all_node_meetings if combining from multiple sources and not pre-sorted
    # For now, get_upcoming_meetings sorts, and if agent_id_filter is used, we only get from one agent.

    return jsonify(all_node_meetings)


@app.route('/transcribe_audio', methods=['POST'])
def transcribe_audio():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500

    data = request.json
    node_id = data.get('node_id') # Target node
    audio_data = data.get('audio_data')
    sender_id = data.get('sender_id') # Get sender ID from request

    # Use node_id as sender if sender_id is not provided (fallback)
    if not sender_id:
        sender_id = node_id
        log_warning(f"Sender ID not provided in /transcribe_audio request, falling back to target node_id: {node_id}")

    if not node_id or not audio_data:
        return jsonify({"error": "Missing node_id or audio_data"}), 400

    if node_id not in network.nodes:
        return jsonify({"error": f"Node {node_id} not found"}), 404

    # Decode the base64 audio data
    try:
        # Remove the data URL prefix if present
        if 'base64,' in audio_data:
            audio_data = audio_data.split('base64,')[1]

        audio_bytes = base64.b64decode(audio_data)

        # Save to a temporary file with mp3 extension
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(audio_bytes)

        print(f"[DEBUG] Audio file saved to {temp_file_path} with size {len(audio_bytes)} bytes")

        # Use Whisper API for transcription
        with open(temp_file_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
                response_format="text"
            )

        # Clean up the temporary file
        os.unlink(temp_file_path)

        # Log the transcript for debugging
        print(f"[DEBUG] Whisper transcription: {transcript}")

        command_text = transcript

        # Remove print override logic
        # response_collector = {"response": None, "terminal_output": []}
        # original_print = print
        # def custom_print(text): ...
        # builtins.print = custom_print

        try:
            # Send the message to the node and get the response directly
            # Use the sender_id obtained from the request
            response_text = network.nodes[node_id].receive_message(command_text, sender_id)

            # Restore original print function (no longer needed)
            # builtins.print = original_print

            # Format terminal output for display (removed - use logs)
            # terminal_text = "\n".join(response_collector["terminal_output"])

            # Generate speech from the direct response
            audio_response = None
            if response_text: # Check if response_text is not None or empty
                try:
                    speech_response = client.audio.speech.create(
                        model="tts-1",
                        voice="alloy",
                        input=response_text # Use the returned text
                    )

                    # Convert to base64 for sending to the client
                    speech_response.write_to_file("temp_speech.mp3")

                    with open("temp_speech.mp3", "rb") as audio_file:
                        audio_response = base64.b64encode(audio_file.read()).decode('utf-8')
                    os.unlink("temp_speech.mp3")
                except Exception as e:
                    print(f"Error generating speech: {str(e)}")

            return jsonify({
                "response": response_text, # Use the returned text
                "terminal_output": "", # Removed unreliable capture
                "transcription": command_text,
                "audio_response": audio_response
            })

        except Exception as e:
            # Restore original print function (no longer needed)
            # builtins.print = original_print
            log_error(f"Error in transcribe_audio processing message: {str(e)}") # Log the error
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        print(f"[DEBUG] Error in audio processing: {str(e)}")
        log_error(f"Error decoding/transcribing audio: {str(e)}") # Log the error
        return jsonify({"error": f"Error processing audio: {str(e)}"}), 500


# Update the existing send_message route to use the common function
@app.route('/send_message', methods=['POST'])
def send_message():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500

    data = request.json
    node_id = data.get('node_id') # Target node
    message = data.get('message')
    sender_id = data.get('sender_id') # Get sender ID from request

    # Use node_id as sender if sender_id is not provided (fallback, though UI should always send it now)
    if not sender_id:
        sender_id = node_id
        log_warning(f"Sender ID not provided in /send_message request, falling back to target node_id: {node_id}")

    if not node_id or not message:
        return jsonify({"error": "Missing node_id or message"}), 400

    if node_id not in network.nodes:
        return jsonify({"error": f"Node {node_id} not found"}), 404

    # Pass the correct sender_id to the internal function
    return send_message_internal(node_id, message, sender_id)


def send_message_internal(node_id, message, sender_id):
    """Process a message sent to a node and return the response"""
    global network
    if not network or node_id not in network.nodes:
        # Handle cases where network or node might not be ready (though checked in caller)
        log_error(f"send_message_internal called for invalid node '{node_id}' or uninitialized network.")
        return jsonify({"error": f"Node {node_id} not found or network unavailable"}), 404

    # Remove print override logic
    # response_collector = {"response": None, "terminal_output": []}
    # original_print = print
    # def custom_print(text): ...
    # builtins.print = custom_print

    try:
        # Send the message to the node and get the response
        # Use the sender_id passed into this function
        log_system_message(f"Routing message to node '{node_id}' from sender '{sender_id}'")
        response_text = network.nodes[node_id].receive_message(message, sender_id)

        # Restore original print function (no longer needed)
        # builtins.print = original_print

        # Format terminal output for display (removed)
        # terminal_text = "\n".join(response_collector["terminal_output"])

        return jsonify({
            "response": response_text, # Use the direct response
            "terminal_output": "" # Removed unreliable capture
        })

    except Exception as e:
        # Restore original print function (no longer needed)
        # builtins.print = original_print
        log_error(f"Error processing message for node {node_id}: {str(e)}") # Log error
        return jsonify({"error": str(e)}), 500


def start_flask():
    # Try different ports if 5000 is in use
    for port in range(5001, 5010):
        try:
            # Use the imported socketio instance to run the app
            print(f"Attempting to start SocketIO server on port {port}")
            # Add allow_unsafe_werkzeug=True if needed for development auto-reloader with SocketIO
            socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
            print(f"SocketIO server started successfully on port {port}")
            break  # Exit loop if successful
        except OSError as e:
            if 'Address already in use' in str(e):
                print(f"Port {port} is in use, trying next port...")
            else:
                print(f"An unexpected OS error occurred: {e}")
                break  # Stop trying if it's not an address-in-use error
        except Exception as e:
            print(f"An unexpected error occurred trying to start the server: {e}")
            break  # Stop trying on other errors


def open_browser():

    # Try different ports
    for port in range(5001, 5010):
        try:
            # Try to connect to check if this is the port being used
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:  # Port is open, server is running here
                webbrowser.open(f'http://localhost:{port}')
                break
        except:
            continue
#obsolete
def run_cli(network):
    print("Commands:\n"
          "  node_id: message => send 'message' to 'node_id' from CLI\n"
          "  node_id: plan project_name = objective => create a new project plan\n"
          "  node_id: tasks => list tasks for a node\n"
          "  quit => exit\n")

    while True:
        user_input = input("> ")
        if user_input.lower().strip() == "quit":
            print("Exiting CLI...")
            break
            
        # Handle node-specific commands
        if ":" in user_input:
            node_id, message = user_input.split(":", 1)
            node_id = node_id.strip()
            message = message.strip()

            if node_id in network.nodes:
                # All commands now go through receive_message
                response = network.nodes[node_id].receive_message(message, "cli_user")
                if response:
                    print(response)
            else:
                print(f"No node with ID '{node_id}' found.")
        else:
            print("Invalid format. Use:\n  node_id: message\n  OR\n  quit\n")

def demo_flexible_meeting(network) -> None:
    """
    Demonstration of flexible meeting scheduling using each assistant's self.brain.calendar.
    Situation:
      - We pre-fill each stakeholder's calendar at different times on May 13, 2025.
      - The CEO then proposes a 30-minute meeting at 10:30, conflicting with Design,
        and the scheduler should suggest an alternative.

    #TODO: Implement this with communication of the personal assistants. 
    #      They should all have the preferences of their users in mind and act accordingly.
    """
    from datetime import datetime, timedelta

    # Ensure every node has a calendar list
    for node in network.nodes:
        network.nodes[node].brain.calendar = []

    date = datetime(2025, 5, 13)

    def block_time(node_id: str, start_hour: int, summary: str):
        node = network.nodes['ceo']
        start_dt = date.replace(hour=start_hour, minute=0, second=0)
        end_dt = start_dt + timedelta(hours=1)
        node.brain.calendar.append({
            'project_id': f'{node_id}_busy',
            'start_time': start_dt.isoformat(),
            'end_time':   end_dt.isoformat(),
            'meeting_info': summary,
            'participants': [node_id],
        })
        print(f"[demo] {node_id} busy: {summary} from {start_dt.time()} to {end_dt.time()}")

    # Block each team at different times
    block_time('engineering', 9,  'Engineering Deep Work')   # 09:00–10:00
    block_time('design',      10, 'Design Review')           # 10:00–11:00
    block_time('marketing',   11, 'Marketing Sync')          # 11:00–12:00

    # # Introduction message
    # intro = (
    #     "You are the CEO.\n"
    #     "• Engineering is busy on 2025-05-13 from 09:00 to 10:00.\n"
    #     "• Design is busy on 2025-05-13 from 10:00 to 11:00.\n"
    #     "• Marketing is busy on 2025-05-13 from 11:00 to 12:00.\n"
    #     "\n"
    #     "Now, to schedule your smart meeting, try something like:\n"
    #     "Please schedule a 30-minute meeting with engineering, design, and marketing "
    #     "on 2025-05-13 at 10:30."
    #     "Title: 'Project X Kickoff'"
    #     "Description: 'Discuss project X requirements and timelines.'\n"
    # )

    # print(f"[demo] ceo: {intro}")   

    # CEO proposes a meeting at 10:30 for 30 minutes (conflicts with Design)
    proposal = (
        "Please schedule a 30-minute meeting with engineering, design, and marketing "
        "on 2025-05-13 at 10:30."
        "Title: 'Project X Kickoff'"
        "Description: 'Discuss project X requirements and timelines.'"
    )
    print(f"[demo] ceo proposes: {proposal}")
    response = network.nodes['ceo'].receive_message(proposal, 'cli_user')
    return (f"[demo] Scheduler response: {response}")

if __name__ == "__main__":
    # Make sure network is initialized before flask starts using it
    network = Intercom(log_file="communication_log.txt") # Use Intercom

    for agent_config in AGENT_CONFIG:
        node = LLMNode(
            node_id=agent_config["id"],
            knowledge=agent_config["knowledge"], # Pass knowledge from config
            network=network,
            llm_api_key_override=openai_api_key
        )
        network.register_node(node.node_id, node)
        log_system_message(f"Created and registered node: {agent_config['id']}")
    # --- End dynamic node creation ---

    # --- Remove static node creation ---
    # ceo = LLMNode("ceo", knowledge="Knows entire org structure.", network=network, llm_api_key_override=openai_api_key)
    # marketing = LLMNode("marketing", knowledge="Knows about markets.", network=network, llm_api_key_override=openai_api_key)
    # engineering = LLMNode("engineering", knowledge="Knows codebase.", network=network, llm_api_key_override=openai_api_key)
    # design = LLMNode("design", knowledge="Knows UI/UX best practices.", network=network, llm_api_key_override=openai_api_key)
    #
    # # Register them using (node_id, node_obj) signature for Intercom
    # network.register_node(ceo.node_id, ceo)
    # network.register_node(marketing.node_id, marketing)
    # network.register_node(engineering.node_id, engineering)
    # network.register_node(design.node_id, design)
    # --- End removal ---

    log_system_message(f"Nodes registered: {network.get_all_nodes()}")

    # Start Flask using the shared socketio instance
    flask_thread = threading.Thread(target=start_flask) 
    flask_thread.daemon = True
    flask_thread.start()

    # Open browser automatically
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    run_cli(network)
    #demo_flexible_meeting(network) # Uncomment to run the demo
    
    # Keep the main thread alive (Flask runs in daemon threads)
    # Or join the flask thread if you want the script to exit when Flask exits
    flask_thread.join() # This would block here
    # Instead, just let the main thread finish, daemon threads will keep running
    log_system_message("Main thread finished, Flask server running in background.")
    # Remove CLI start if not needed
    # run_cli(network)


# --- Add CV Upload Route ---
@app.route('/upload_cv', methods=['POST'])
def upload_cv_route():
    if 'cv_file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['cv_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Ensure the filename ends with .pdf (case-insensitive)
    if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() == 'pdf':
        temp_file_path = None  # Initialize path variable
        try:
            # Create a temporary file to store the PDF
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                file.save(temp_pdf.name)
                temp_file_path = temp_pdf.name

            print(f"[CV Parser] Temporary file saved at: {temp_file_path}")

            # Instantiate the parser and parse the CV
            # Ensure OPENAI_API_KEY is available in the environment where CVParser runs
            # parser = CVParser()
            # cv_data = parser.parse_cv(temp_file_path)

            # Check if parsing was successful
            # if cv_data is None:
            #    print("[CV Parser] Parsing failed, cv_data is None.")
            #    return jsonify({"error": "Could not parse CV file. Check server logs for details."}), 500

            # Return the extracted data successfully
            print("[CV Parser] Parsing successful.")
            return jsonify({
                'success': True,
                #    'summary': cv_data # Contains name, email, phone, education, work_experience, skills
            }), 200

        except Exception as e:
            # Log the error for debugging
            print(f"[CV Parser] Error processing CV: {str(e)}")
            # Return a generic error message to the client
            return jsonify({'error': f"An unexpected error occurred while processing the CV."}), 500
        finally:
            # --- Ensure temporary file cleanup ---
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    print(f"[CV Parser] Temporary file deleted: {temp_file_path}")
                except Exception as cleanup_e:
                    # Log cleanup error but don't necessarily fail the request
                    print(f"[CV Parser] Error deleting temp file during cleanup: {cleanup_e}")
            # --- End cleanup ---

    else:
        # File is not a PDF or has no extension
        return jsonify({"error": "Invalid file type. Please upload a PDF file."}), 400
# --- End CV Upload Route ---