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
from flask import Flask, render_template, jsonify, request
import threading
import webbrowser
from flask_cors import CORS

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

client = openai.OpenAI(api_key=api_key)
if not client.api_key:
    raise ValueError("Please set OPENAI_API_KEY in environment variables or .env file")

# Add these constants at the top level
SCOPES = ['https://www.googleapis.com/auth/calendar']
CLIENT_ID = '473172815719-1vso4g75vqfe4p312ngp1htdjgeeve5g.apps.googleusercontent.com'
TOKEN_FILE = 'token.pickle'

# Define task structure
class Task:
    def __init__(self, title: str, description: str, due_date: datetime, 
                 assigned_to: str, priority: str, project_id: str):
        self.title = title
        self.description = description
        self.due_date = due_date
        self.assigned_to = assigned_to
        self.priority = priority
        self.project_id = project_id
        self.completed = False
        self.id = f"task_{hash(title + assigned_to + str(due_date))}"
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date.isoformat(),
            "assigned_to": self.assigned_to,
            "priority": self.priority,
            "project_id": self.project_id,
            "completed": self.completed
        }
    
    def __str__(self):
        return f"{self.title} - Due: {self.due_date.strftime('%Y-%m-%d')} - Assigned to: {self.assigned_to}"

class Network:
    def __init__(self, log_file: Optional[str] = None):
        self.nodes: Dict[str, LLMNode] = {}
        self.log_file = log_file
        self.tasks: List[Task] = []

    def register_node(self, node: 'LLMNode'):
        self.nodes[node.node_id] = node
        node.network = self

    def send_message(self, sender_id: str, recipient_id: str, content: str):
        self._log_message(sender_id, recipient_id, content)

        if recipient_id in self.nodes:
            self.nodes[recipient_id].receive_message(content, sender_id)
        else:
            print(f"Node {recipient_id} not found in the network.")

    def _log_message(self, sender_id: str, recipient_id: str, content: str):
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"From {sender_id} to {recipient_id}: {content}\n")
    
    def add_task(self, task: Task):
        self.tasks.append(task)
        # Notify the assigned person
        if task.assigned_to in self.nodes:
            message = f"New task assigned: {task.title}. Due: {task.due_date.strftime('%Y-%m-%d')}. Priority: {task.priority}."
            self.send_message("system", task.assigned_to, message)
    
    def get_tasks_for_node(self, node_id: str) -> List[Task]:
        return [task for task in self.tasks if task.assigned_to == node_id]


class LLMNode:
    def __init__(self, node_id: str, knowledge: str = "",
                 llm_api_key: str = "", llm_params: dict = None):
        """
        Node representing a user/agent, each with its own knowledge and mini-world (projects, calendar, etc.).
        """
        self.node_id = node_id
        self.knowledge = knowledge

        # If each node can have its own API key, set it here. Otherwise, use the shared client.
        self.llm_api_key = llm_api_key
        self.client = client if not self.llm_api_key else openai.OpenAI(api_key=self.llm_api_key)

        # Tuning LLM params for concise answers
        self.llm_params = llm_params if llm_params else {
            "model": "gpt-4o-mini",
            "temperature": 0.1,        # Very low => short, deterministic
            "max_tokens": 1000         # Enough tokens but not huge
        }

        # Store conversation if needed
        self.conversation_history = []

        # For multiple projects, store them in a dict: { project_id: {...}, ... }
        self.projects = {}

        # Calendar for meeting scheduling
        self.calendar = []
        # Uncomment calendar service initialization
        self.calendar_service = self._get_calendar_service()

        self.network: Optional[Network] = None

    # Uncomment the calendar service method
    def _get_calendar_service(self):
        """Initialize Google Calendar service with improved error handling"""
        print(f"[{self.node_id}] Initializing Google Calendar service...")
        
        # Check if client secret is available
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        if not client_secret:
            print(f"[{self.node_id}] ERROR: GOOGLE_CLIENT_SECRET environment variable not found")
            return None
        
        print(f"[{self.node_id}] Client secret found: {client_secret[:5]}...")
        
        creds = None
        if os.path.exists(TOKEN_FILE):
            print(f"[{self.node_id}] Found existing token file")
            try:
                with open(TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)
                print(f"[{self.node_id}] Successfully loaded credentials from token file")
            except Exception as e:
                print(f"[{self.node_id}] Error loading token file: {str(e)}")
        else:
            print(f"[{self.node_id}] No token file found at {TOKEN_FILE}")
        
        try:
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    print(f"[{self.node_id}] Refreshing expired credentials")
                    creds.refresh(Request())
                    print(f"[{self.node_id}] Credentials refreshed successfully")
                else:
                    print(f"[{self.node_id}] Starting new OAuth flow with client ID: {CLIENT_ID[:10]}...")
                    client_config = {
                        "installed": {
                            "client_id": CLIENT_ID,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                            "redirect_uris": ["http://localhost:8080/"]
                        }
                    }
                    
                    try:
                        flow = InstalledAppFlow.from_client_config(
                            client_config,
                            scopes=SCOPES
                        )
                        print(f"[{self.node_id}] OAuth flow created successfully")
                        print(f"[{self.node_id}] Running local server for authentication on port 8080...")
                        print(f"[{self.node_id}] Please check your browser. If no browser opens, go to http://localhost:8080")
                        creds = flow.run_local_server(port=8080)
                        print(f"[{self.node_id}] Authentication successful")
                    except Exception as e:
                        print(f"[{self.node_id}] Authentication error: {str(e)}")
                        print(f"[{self.node_id}] Full error details: {repr(e)}")
                        return None

                print(f"[{self.node_id}] Saving credentials to token file: {TOKEN_FILE}")
                try:
                    with open(TOKEN_FILE, 'wb') as token:
                        pickle.dump(creds, token)
                    print(f"[{self.node_id}] Credentials saved successfully")
                except Exception as e:
                    print(f"[{self.node_id}] Error saving credentials: {str(e)}")

            print(f"[{self.node_id}] Building calendar service...")
            service = build('calendar', 'v3', credentials=creds)
            
            # Test the service with a simple API call
            print(f"[{self.node_id}] Testing calendar service with calendarList.list()...")
            calendar_list = service.calendarList().list().execute()
            print(f"[{self.node_id}] Calendar service working! Found {len(calendar_list.get('items', []))} calendars")
            
            return service
        except Exception as e:
            print(f"[{self.node_id}] Failed to build or test calendar service: {str(e)}")
            print(f"[{self.node_id}] Full error details: {repr(e)}")
            return None

    # Uncomment the calendar reminder method
    def create_calendar_reminder(self, task: Task):
        """Create a Google Calendar reminder for a task"""
        if not self.calendar_service:
            print(f"[{self.node_id}] Calendar service not available, skipping reminder creation")
            return
            
        try:
            event = {
                'summary': f"TASK: {task.title}",
                'description': f"{task.description}\n\nPriority: {task.priority}\nProject: {task.project_id}",
                'start': {
                    'dateTime': task.due_date.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': (task.due_date + timedelta(hours=1)).isoformat(),
                    'timeZone': 'UTC',
                },
                'attendees': [{'email': f'{task.assigned_to}@example.com'}],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 60}         # 1 hour before
                    ]
                }
            }
            
            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            print(f"[{self.node_id}] Task reminder created: {event.get('htmlLink')}")
            
        except Exception as e:
            print(f"[{self.node_id}] Failed to create calendar reminder: {e}")

    # Replace the local meeting scheduling with Google Calendar version
    def schedule_meeting(self, project_id: str, participants: list):
        """Updated to use Google Calendar"""
        # If calendar service is not available, fall back to local scheduling
        if not self.calendar_service:
            print(f"[{self.node_id}] Calendar service not available, using local scheduling")
            self._fallback_schedule_meeting(project_id, participants)
            return
            
        meeting_description = f"Meeting for project '{project_id}'"
        
        # Create event
        event = {
            'summary': meeting_description,
            'start': {
                'dateTime': (datetime.now() + timedelta(days=1)).isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': (datetime.now() + timedelta(days=1, hours=1)).isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': [{'email': f'{p}@example.com'} for p in participants],
        }

        try:
            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            print(f"[{self.node_id}] Meeting created: {event.get('htmlLink')}")
            
            # Store in local calendar as well
            self.calendar.append({
                'project_id': project_id,
                'meeting_info': meeting_description,
                'event_id': event['id']
            })

            # Notify other participants
            for p in participants:
                if p in self.network.nodes:
                    self.network.nodes[p].calendar.append({
                        'project_id': project_id,
                        'meeting_info': meeting_description,
                        'event_id': event['id']
                    })
                    print(f"[{self.node_id}] Notified {p} about meeting for project '{project_id}'.")
        except Exception as e:
            print(f"[{self.node_id}] Failed to create calendar event: {e}")
            # Fallback to local calendar
            self._fallback_schedule_meeting(project_id, participants)
    
    # Uncomment the fallback method
    def _fallback_schedule_meeting(self, project_id: str, participants: list):
        """Local fallback for scheduling when Google Calendar fails"""
        meeting_info = f"Meeting for project '{project_id}' scheduled for {datetime.now() + timedelta(days=1)}"
        self.calendar.append({
            'project_id': project_id,
            'meeting_info': meeting_info
        })
        
        print(f"[{self.node_id}] Scheduled local meeting: {meeting_info}")
        
        # Notify other participants
        for p in participants:
            if p in self.network.nodes:
                self.network.nodes[p].calendar.append({
                    'project_id': project_id,
                    'meeting_info': meeting_info
                })
                print(f"[{self.node_id}] Notified {p} about meeting for project '{project_id}'.")

    def receive_message(self, message: str, sender_id: str):
        """
        Receives a message from another node or user. We only generate an LLM reply
        if the sender is the CLI user (i.e., "cli_user"). This prevents node-to-node
        loops of "Goodbye".
        """
        print(f"[{self.node_id}] Received from {sender_id}: {message}")

        # Check for calendar-related commands in natural language
        if sender_id == "cli_user":
            # Check for meeting creation request with more patterns
            if any(phrase in message.lower() for phrase in [
                "schedule", "set up", "create", "organize", "arrange", "plan a meeting", 
                "meeting with", "meet with", "get together with"
            ]):
                print(f"[{self.node_id}] Detected meeting creation request")
                self._handle_meeting_creation(message)
                return
            
            # Check for meeting cancellation request
            if any(phrase in message.lower() for phrase in [
                "cancel", "delete", "remove", "call off", "postpone", "reschedule"
            ]) and any(word in message.lower() for word in ["meeting", "appointment", "call"]):
                print(f"[{self.node_id}] Detected meeting cancellation request")
                self._handle_meeting_cancellation(message)
                return

        # Record the incoming user message in the conversation history
        self.conversation_history.append({"role": "user", "content": f"{sender_id} says: {message}"})

        # ---- KEY CHANGE ----
        # Only respond with LLM if the message came directly from the CLI user.
        # If "ceo" or "marketing" or any node sends a message, we do NOT auto-respond.
        if sender_id == "cli_user":
            response = self.query_llm(self.conversation_history)
            self.conversation_history.append({"role": "assistant", "content": response})
            # Just print the response instead of trying to send it back
            print(f"[{self.node_id}] Response: {response}")

    def send_message(self, recipient_id: str, content: str):
        if not self.network:
            print(f"[{self.node_id}] No network attached.")
            return
        
        # Special case for CLI user
        if recipient_id == "cli_user":
            print(f"[{self.node_id}] Response: {content}")
        else:
            self.network.send_message(self.node_id, recipient_id, content)

    def query_llm(self, messages):
        """
        We'll use a system prompt that instructs the LLM to be short, direct, and not loop forever.
        """
        system_prompt = [{
            "role": "system",
            "content": (
                "You are a direct and concise AI agent for an organization. "
                "Provide short, to-the-point answers and do not continue repeating Goodbyes. "
                "End after conveying necessary information."
            )
        }]

        combined_messages = system_prompt + messages
        try:
            completion = self.client.chat.completions.create(
                model=self.llm_params["model"],
                messages=combined_messages,
                temperature=self.llm_params["temperature"],
                max_tokens=self.llm_params["max_tokens"]
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[{self.node_id}] LLM query failed: {e}")
            return "LLM query failed."

    def plan_project(self, project_id: str, objective: str):
        """
        Create a detailed project plan, parse it, notify roles, then schedule a meeting for them.
        """
        if project_id not in self.projects:
            self.projects[project_id] = {
                "name": objective,
                "plan": [],
                "participants": set()
            }

        plan_prompt = f"""
        You are creating a detailed project plan for project '{project_id}'.
        Objective: {objective}

        The plan should include:
        1. All stakeholders involved in the project. Use only these roles: CEO, Marketing, Engineering, Design.
        2. Detailed steps needed to execute the plan, including time and cost estimates.
        Each step should be written in paragraphs and full sentences.

        Return valid JSON only, with this structure:
        {{
          "stakeholders": ["list of stakeholders"],
          "steps": [
            {{
              "description": "Detailed step description with time and cost estimates"
            }}
          ]
        }}
        Keep it concise. End after providing the JSON. No extra words.
        """

        response = self.query_llm([{"role": "user", "content": plan_prompt}])
        print(f"[{self.node_id}] LLM raw response (project '{project_id}'): {response}")

        try:
            data = json.loads(response)
            stakeholders = data.get("stakeholders", [])
            steps = data.get("steps", [])
            self.projects[project_id]["plan"] = steps

            # Write the plan to a text file
            with open(f"{project_id}_plan.txt", "w", encoding="utf-8") as file:
                file.write(f"Project ID: {project_id}\n")
                file.write(f"Objective: {objective}\n")
                file.write("Stakeholders:\n")
                for stakeholder in stakeholders:
                    file.write(f"  - {stakeholder}\n")
                file.write("Steps:\n")
                for step in steps:
                    file.write(f"  - {step.get('description', '')}\n")

            # Improved role mapping with case-insensitive matching
            role_to_node = {
                "ceo": "ceo",
                "marketing": "marketing",
                "engineering": "engineering",
                "design": "design"
            }

            participants = []
            for stakeholder in stakeholders:
                # Normalize the role name (lowercase and remove extra spaces)
                role = stakeholder.lower().strip()
                
                # Check for partial matches
                matched = False
                for key in role_to_node:
                    if key in role:
                        node_id = role_to_node[key]
                        participants.append(node_id)
                        self.projects[project_id]["participants"].add(node_id)
                        matched = True
                        break
                
                if not matched:
                    print(f"[{self.node_id}] No mapping for stakeholder '{stakeholder}'. Skipping.")

            print(f"[{self.node_id}] Project participants: {participants}")
            
            # Schedule a meeting
            self.schedule_meeting(project_id, participants)
            
            # Generate tasks from the plan
            self.generate_tasks_from_plan(project_id, steps, participants)
            
        except json.JSONDecodeError as e:
            print(f"[{self.node_id}] Failed to parse JSON plan: {e}")

    def generate_tasks_from_plan(self, project_id: str, steps: list, participants: list):
        """Generate tasks from project plan steps using OpenAI function calling"""
        
        # Define the function for task creation
        functions = [
            {
                "type": "function",
                "function": {
                    "name": "create_task",
                    "description": "Create a task from a project step",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Short title for the task"
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed description of what needs to be done"
                            },
                            "assigned_to": {
                                "type": "string",
                                "description": "Role responsible for this task (marketing, engineering, design, ceo)"
                            },
                            "due_date_offset": {
                                "type": "integer",
                                "description": "Days from now when the task is due"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "Priority level of the task"
                            }
                        },
                        "required": ["title", "description", "assigned_to", "due_date_offset", "priority"]
                    }
                }
            }
        ]
        
        # For each step, generate tasks
        for i, step in enumerate(steps):
            step_description = step.get("description", "")
            
            prompt = f"""
            For project '{project_id}', analyze this step and create appropriate tasks:
            
            Step: {step_description}
            
            Available roles: {', '.join(participants)}
            
            Create 1-3 specific tasks from this step. Each task should be assigned to the most appropriate role.
            """
            
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",  # Using a more capable model for task generation
                    messages=[{"role": "user", "content": prompt}],
                    tools=functions,
                    tool_choice={"type": "function", "function": {"name": "create_task"}}
                )
                
                # Process the function calls
                for choice in response.choices:
                    if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                        for tool_call in choice.message.tool_calls:
                            if tool_call.function.name == "create_task":
                                task_data = json.loads(tool_call.function.arguments)
                                
                                # Create the task
                                due_date = datetime.now() + timedelta(days=task_data["due_date_offset"])
                                task = Task(
                                    title=task_data["title"],
                                    description=task_data["description"],
                                    due_date=due_date,
                                    assigned_to=task_data["assigned_to"],
                                    priority=task_data["priority"],
                                    project_id=project_id
                                )
                                
                                # Add to network tasks
                                if self.network:
                                    self.network.add_task(task)
                                    print(f"[{self.node_id}] Created task: {task}")
                                    
                                    # Uncomment the calendar reminder
                                    self.create_calendar_reminder(task)
            
            except Exception as e:
                print(f"[{self.node_id}] Error generating tasks for step {i+1}: {e}")

    def list_tasks(self):
        """List all tasks assigned to this node"""
        if not self.network:
            return "No network connected."
            
        tasks = self.network.get_tasks_for_node(self.node_id)
        if not tasks:
            return f"No tasks assigned to {self.node_id}."
            
        result = f"Tasks for {self.node_id}:\n"
        for i, task in enumerate(tasks, 1):
            result += f"{i}. {task.title} (Due: {task.due_date.strftime('%Y-%m-%d')}, Priority: {task.priority})\n"
            result += f"   Description: {task.description}\n"
            
        return result

    def _handle_meeting_creation(self, message):
        """Handle natural language meeting creation requests"""
        # Use OpenAI to extract meeting details
        prompt = f"""
        Extract meeting details from this message: "{message}"
        
        Return a JSON object with these fields:
        - title: The meeting title or topic
        - participants: Array of participants (use only: ceo, marketing, engineering, design)
        - date: Meeting date (YYYY-MM-DD format) or "tomorrow" if not specified
        - time: Meeting time (HH:MM format) or "10:00" if not specified
        - duration: Duration in minutes (default to 60 if not specified)
        
        Only include participants that are explicitly mentioned or clearly implied.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            meeting_data = json.loads(response.choices[0].message.content)
            
            # Process participants
            participants = []
            for p in meeting_data.get("participants", []):
                p_lower = p.lower().strip()
                if p_lower in ["ceo", "marketing", "engineering", "design"]:
                    participants.append(p_lower)
            
            # Add the current node if not already included
            if self.node_id not in participants:
                participants.append(self.node_id)
            
            # Process date/time
            meeting_date = meeting_data.get("date", "tomorrow")
            if meeting_date == "tomorrow":
                meeting_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            meeting_time = meeting_data.get("time", "10:00")
            duration_mins = int(meeting_data.get("duration", 60))
            
            # Create datetime objects
            start_datetime = datetime.strptime(f"{meeting_date} {meeting_time}", "%Y-%m-%d %H:%M")
            end_datetime = start_datetime + timedelta(minutes=duration_mins)
            
            # Create a unique project ID for this meeting
            meeting_id = f"meeting_{int(datetime.now().timestamp())}"
            meeting_title = meeting_data.get("title", f"Meeting scheduled by {self.node_id}")
            
            # Schedule the meeting
            self._create_calendar_meeting(meeting_id, meeting_title, participants, start_datetime, end_datetime)
            
            # Confirm to user
            print(f"[{self.node_id}] Meeting '{meeting_title}' scheduled for {meeting_date} at {meeting_time} with {', '.join(participants)}")
            
        except Exception as e:
            print(f"[{self.node_id}] Error creating meeting: {str(e)}")

    def _handle_meeting_cancellation(self, message):
        """Handle natural language meeting cancellation requests"""
        # First, get all meetings from calendar
        if not self.calendar_service:
            print(f"[{self.node_id}] Calendar service not available, can't cancel meetings")
            return
        
        try:
            # Use OpenAI to extract cancellation details
            prompt = f"""
            Extract meeting cancellation details from this message: "{message}"
            
            Return a JSON object with these fields:
            - title: The meeting title or topic to cancel (or null if not specified)
            - with_participants: Array of participants in the meeting to cancel (or empty if not specified)
            - date: Meeting date to cancel (YYYY-MM-DD format, or null if not specified)
            
            Only include information that is explicitly mentioned.
            """
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            cancel_data = json.loads(response.choices[0].message.content)
            
            # Get upcoming meetings
            now = datetime.utcnow().isoformat() + 'Z'
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            if not events:
                print(f"[{self.node_id}] No upcoming meetings found to cancel")
                return
            
            # Filter events based on cancellation criteria
            title_filter = cancel_data.get("title")
            participants_filter = [p.lower() for p in cancel_data.get("with_participants", [])]
            date_filter = cancel_data.get("date")
            
            cancelled_count = 0
            for event in events:
                should_cancel = True
                
                # Check title match if specified
                if title_filter and title_filter.lower() not in event.get('summary', '').lower():
                    should_cancel = False
                
                # Check participants if specified
                if participants_filter:
                    event_attendees = [a.get('email', '').split('@')[0].lower() 
                                      for a in event.get('attendees', [])]
                    if not any(p in event_attendees for p in participants_filter):
                        should_cancel = False
                
                # Check date if specified
                if date_filter:
                    event_start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date'))
                    if event_start and date_filter not in event_start:
                        should_cancel = False
                
                if should_cancel:
                    # Cancel the meeting
                    self.calendar_service.events().delete(
                        calendarId='primary',
                        eventId=event['id']
                    ).execute()
                    
                    # Remove from local calendar
                    self.calendar = [m for m in self.calendar if m.get('event_id') != event['id']]
                    
                    # Notify participants
                    event_attendees = [a.get('email', '').split('@')[0] for a in event.get('attendees', [])]
                    for attendee in event_attendees:
                        if attendee in self.network.nodes:
                            # Update their local calendar
                            self.network.nodes[attendee].calendar = [
                                m for m in self.network.nodes[attendee].calendar 
                                if m.get('event_id') != event['id']
                            ]
                            # Notify them
                            notification = f"Meeting '{event.get('summary')}' has been cancelled by {self.node_id}"
                            self.network.send_message(self.node_id, attendee, notification)
                
                    cancelled_count += 1
                    print(f"[{self.node_id}] Cancelled meeting: {event.get('summary')}")
            
            if cancelled_count == 0:
                print(f"[{self.node_id}] No meetings found matching the cancellation criteria")
            else:
                print(f"[{self.node_id}] Cancelled {cancelled_count} meeting(s)")
            
        except Exception as e:
            print(f"[{self.node_id}] Error cancelling meeting: {str(e)}")

    def _create_calendar_meeting(self, meeting_id, title, participants, start_datetime, end_datetime):
        """Create a calendar meeting with the specified details"""
        # If calendar service is not available, fall back to local scheduling
        if not self.calendar_service:
            print(f"[{self.node_id}] Calendar service not available, using local scheduling")
            self._fallback_schedule_meeting(meeting_id, participants)
            return
        
        # Create event
        event = {
            'summary': title,
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': [{'email': f'{p}@example.com'} for p in participants],
        }

        try:
            event = self.calendar_service.events().insert(calendarId='primary', body=event).execute()
            print(f"[{self.node_id}] Meeting created: {event.get('htmlLink')}")
            
            # Store in local calendar as well
            self.calendar.append({
                'project_id': meeting_id,
                'meeting_info': title,
                'event_id': event['id']
            })

            # Notify other participants
            for p in participants:
                if p != self.node_id and p in self.network.nodes:
                    self.network.nodes[p].calendar.append({
                        'project_id': meeting_id,
                        'meeting_info': title,
                        'event_id': event['id']
                    })
                    notification = f"New meeting: '{title}' scheduled by {self.node_id} for {start_datetime.strftime('%Y-%m-%d %H:%M')}"
                    self.network.send_message(self.node_id, p, notification)
        except Exception as e:
            print(f"[{self.node_id}] Failed to create calendar event: {e}")
            # Fallback to local calendar
            self._fallback_schedule_meeting(meeting_id, participants)


def run_cli(network):
    print("Commands:\n"
          "  node_id: message => send 'message' to 'node_id' from CLI\n"
          "  node_id: plan project_name = objective => create a new project plan\n"
          "  node_id: tasks => list tasks for a node\n"
          "  quit => exit\n")

    while True:
        user_input = input("> ")
        if user_input.lower().strip() == "quit":
            print("Exiting chat...\n")
            print("\n===== Final State of Each Node =====")
            for node_id, node in network.nodes.items():
                print(f"\n--- Node: {node_id} ---")
                print("Calendar:", node.calendar)
                print("Projects:", node.projects)
                print("Tasks:", network.get_tasks_for_node(node_id))
                print("Conversation History:", node.conversation_history)
            break

        # Plan project command
        if "plan" in user_input and "=" in user_input:
            try:
                # e.g. "ceo: plan p123 = Build AI feature"
                parts = user_input.split(":", 1)
                if len(parts) != 2:
                    print("Invalid format. Use: node_id: plan project_name = objective")
                    continue
                    
                node_id = parts[0].strip()
                command_part = parts[1].strip()
                
                # Extract everything after "plan" keyword
                if "plan" not in command_part:
                    print("Command must include the word 'plan'")
                    continue
                    
                plan_part = command_part.split("plan", 1)[1].strip()
                
                if "=" not in plan_part:
                    print("Invalid format. Missing '=' between project name and objective")
                    continue
                    
                project_id_part, objective_part = plan_part.split("=", 1)
                project_id = project_id_part.strip()
                objective = objective_part.strip()

                if node_id in network.nodes:
                    network.nodes[node_id].plan_project(project_id, objective)
                else:
                    print(f"No node found: {node_id}")
            except Exception as e:
                print(f"Error parsing plan command: {str(e)}")
        # List tasks command
        elif "tasks" in user_input:
            try:
                node_id = user_input.split(":", 1)[0].strip()
                if node_id in network.nodes:
                    tasks_list = network.nodes[node_id].list_tasks()
                    print(tasks_list)
                else:
                    print(f"No node found: {node_id}")
            except Exception as e:
                print(f"Error listing tasks: {e}")
        else:
            # normal message command: "node_id: some message"
            if ":" not in user_input:
                print("Invalid format. Use:\n  node_id: message\nOR\n  node_id: plan project_name = objective\nOR\n  node_id: tasks\n")
                continue
            node_id, message = user_input.split(":", 1)
            node_id = node_id.strip()
            message = message.strip()

            if node_id in network.nodes:
                # The CLI user sends a message to the node
                network.nodes[node_id].receive_message(message, "cli_user")
            else:
                print(f"No node with ID '{node_id}' found.")


# Modify the Flask app initialization
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
network = None  # Will be set by the main function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tasks')
def show_tasks():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500
    
    all_tasks = []
    for node_id, node in network.nodes.items():
        tasks = network.get_tasks_for_node(node_id)
        for task in tasks:
            all_tasks.append(task.to_dict())
    
    return jsonify(all_tasks)

@app.route('/nodes')
def show_nodes():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500
    
    nodes = list(network.nodes.keys())
    return jsonify(nodes)

@app.route('/projects')
def show_projects():
    global network
    if not network:
        return jsonify({"error": "Network not initialized"}), 500
    
    all_projects = {}
    for node_id, node in network.nodes.items():
        for project_id, project in node.projects.items():
            if project_id not in all_projects:
                all_projects[project_id] = {
                    "name": project.get("name", ""),
                    "participants": list(project.get("participants", set())),
                    "owner": node_id
                }
    
    return jsonify(all_projects)

def start_flask():
    # Try different ports if 5000 is in use
    for port in range(5001, 5010):
        try:
            app.run(debug=False, host='0.0.0.0', port=port)
            break
        except OSError:
            print(f"Port {port} is in use, trying next port...")

def open_browser():
    # Wait a bit for Flask to start
    import time
    time.sleep(1.5)
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

def demo_run():
    global network
    network = Network(log_file="communication_log.txt")

    # Create nodes
    ceo = LLMNode("ceo", knowledge="Knows entire org structure.")
    marketing = LLMNode("marketing", knowledge="Knows about markets.")
    engineering = LLMNode("engineering", knowledge="Knows codebase.")
    design = LLMNode("design", knowledge="Knows UI/UX best practices.")

    # Register them
    network.register_node(ceo)
    network.register_node(marketing)
    network.register_node(engineering)
    network.register_node(design)

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True  # This ensures the thread will exit when the main program exits
    flask_thread.start()
    
    # Open browser automatically
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    # Start the CLI
    run_cli(network)


if __name__ == "__main__":
    demo_run()
