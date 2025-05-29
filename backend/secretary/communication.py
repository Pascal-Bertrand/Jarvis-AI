import re
import base64
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone 

from secretary.utilities.logging import log_user_message, log_network_message, log_warning, log_system_message, log_error
from secretary.utilities.google import initialize_google_services
from secretary.scheduler import Scheduler
from secretary.brain import Confirmation

class Communication:
    """
    Handles external communication for the node, including CLI and network interactions.
    Delegates all calendar operations to the Scheduler module.

    Stages in receive_message:
      1) Quick CLI commands (tasks, plan)
      2) Calendar commands → Scheduler.handle_calendar()
      3) Email commands (send + advanced)
      4) Fallback → LLM conversation
    """

    def __init__(self, node_id: str, llm_client, network, open_api_key: str):
        """
        Initialize the Communication handler.

        Args:
            node_id (str): Identifier for this node.
            llm_client: Wrapped LLM interface for chat.
            network: The Intercom/network instance for message routing.
            user_id (str): The user ID this communication handler belongs to.
        """
        self.node_id = node_id
        self.llm = llm_client
        self.network = network
        self.open_api_key = open_api_key
        #self.user_id = user_id  # Store user ID for data isolation

        # Data stores for tasks, projects, meetings
        self.tasks: List = []
        self.projects: Dict = {}
        self.meetings: List = []

        # Conversation history for LLM
        self.conversation_history: List[Dict] = []

        # --- ADD Placeholders for injected dependencies ---
        self.brain = None  # Will be injected by LLMNode
        self.scheduler = None # Will be injected by LLMNode
        self.calendar_service = None # Will be injected by LLMNode
        self.gmail_service = None # Will be injected by LLMNode

    def receive_message(self, message: str, sender_id: str) -> Optional[str]:
        """
        Process an incoming message in four steps:
          1) Quick CLI commands
          2) Calendar commands (delegated to Scheduler)
          3) Email commands
          4) Fallback chat via LLM

        Args:
            message (str): The incoming message text.
            sender_id (str): Who sent the message (e.g. a node ID).
            
        Returns:
            Optional[str]: The textual response to be sent back, or None if handled internally.
        """
        
        # Log the message
        log_system_message(f"[Communication] {sender_id, self.node_id, message}")
        print(f"[{self.node_id}] Received from {sender_id}: {message}")

        # Check if it is a information message from another node
        if message.startswith("[(INFO)]"):
            log_system_message(f"[Communication] [{self.node_id}] Information message: {message.replace('[(INFO)]', '')}")
            return message.replace("[(INFO)]", "")        

        # quick CLI command handling
        quick_cmd_response = self._handle_quick_command(message, sender_id)
        if quick_cmd_response is not None:
            log_system_message(f"[Communication] Quick command response: {quick_cmd_response}")
            return quick_cmd_response

        # Check if the message is the response to a confirmation question
        if self.brain and self.brain.confirmation_context['active'] == True:
            log_system_message(f"[Communication] Confirmation response: {message}")
            
            if Confirmation.request(self, message):
                self.brain.confirmation_context['active'] = False
                return self._handle_confirmation_response(message, sender_id)
            else:
                self.brain.confirmation_context['active'] = False
                return "No problem, let me know if you need anything else."

        # Calendar commands -> delegate entirely to Scheduler
        if self.scheduler:
            cal_intent = self.brain._detect_calendar_intent(message)
            log_system_message(f"[Communication] Calendar intent detected: {cal_intent}")
            if cal_intent.get('is_calendar_command', False):
                log_system_message(f"[Communication] Routing calendar command to scheduler")
                return self.scheduler.handle_calendar(cal_intent, message)
            if self.brain.meeting_context['active'] == True:
                log_system_message(f"[Communication] Meeting creation in progress")
                return self.scheduler._continue_meeting_creation(message, sender_id)

        # Email commands - only check if message looks like an email-related command
        # Simple heuristic to avoid unnecessary LLM calls for non-email messages
        email_keywords = ["email", "gmail", "mail", "inbox", "message", "send", "write", "compose", "draft"]
        if any(keyword in message.lower() for keyword in email_keywords) and self.brain:
            # First, check for advanced commands (like search, list labels) which should return a response
            adv_email_analysis = self.brain._analyze_email_command(message)
            if adv_email_analysis.get('action') in ['list_labels', 'advanced_search', 'fetch_recent', 'search']:
                return self.brain.process_advanced_email_command(adv_email_analysis)
                
            # Then, check for send email intent
            send_email_intent = self.brain._detect_send_email_intent(message)
            if send_email_intent.get('is_send_email', False):
                # Email composition might be multi-turn, handle appropriately
                return self._handle_email_composition(send_email_intent, message)

        # Fallback: send to LLM
        return self._chat_with_llm(message)
    
    def _handle_confirmation_response(self, message: str, sender_id: str) -> Optional[str]:
        """
        Handle the response to a confirmation question.

        Args:
            message (str): The response message from the user.
            sender_id (str): The ID of the sender.

        Returns:
            Optional[str]: Response string based on confirmation.
        """
        
        if self.brain.confirmation_context['context'] == 'schedule meeting':
            meeting_id = f"meeting_{int(datetime.now().timestamp())}"
            meeting_title = self.brain.meeting_context['collected_info'].get('title', 'Meeting')
            participants = self.brain.meeting_context['collected_info'].get('participants', [])
            print(participants, meeting_title)
            proposed_start = self.brain.confirmation_context['start_datetime']
            proposed_end = self.brain.confirmation_context['end_datetime']
            return self.scheduler._create_calendar_meeting(meeting_id, meeting_title, participants, proposed_start, proposed_end)
        
        if self.brain.confirmation_context['context'] == 'plan project':
            return self.brain.finalize_and_plan_project(self.brain.confirmation_context['project_id'])
            

    def _handle_quick_command(self, message: str, sender_id: str) -> Optional[str]:
        """
        Single-turn commands from CLI: 'tasks' and project/task management commands.

        Supported commands:
        - 'tasks': List all tasks
        - 'plan <project_id>=<objective>': Create a new project
        - 'create project <project_id> <objective>': Alternative syntax for project creation
        - 'new project <project_id> <objective>': Alternative syntax for project creation
        - 'start project <project_id> <objective>': Alternative syntax for project creation
        - 'project <project_id> <objective>': Simple syntax for project creation
        - 'generate tasks for <project_id>': Generate tasks for existing project
        - 'create tasks for <project_id>': Alternative syntax for task generation
        - 'make tasks for <project_id>': Alternative syntax for task generation

        Returns: 
            Optional[str]: Response string if command handled, None otherwise.
        """
        if not self.brain:
            return None

        cmd = message.strip().lower()
        
        # Command: List all tasks
        if cmd == 'tasks' or cmd == 'list tasks' or cmd == 'show tasks':
            log_system_message(f"[Communication] Quick command: Listing tasks")
            tasks_list = self.brain.list_tasks()
            return tasks_list
        
        # Command: Create project with 'plan <project_id>=<objective>' syntax
        plan_match = re.match(r"^plan\s+([\w-]+)\s*=\s*(.+)$", message.strip(), re.IGNORECASE | re.DOTALL)
        if plan_match:
            log_system_message(f"[Communication] Quick command: Creating project with plan_match")
            project_id, objective = plan_match.groups()
            plan_summary = self.brain.initiate_project_planning(project_id.strip(), objective.strip())
            return plan_summary
        
        # Command: Create project with 'create/new/start project <project_id> <objective>' syntax
        create_project_match = re.match(r"^(create|new|start)?\s*project\s+([\w-]+)\s+(.+)$", message.strip(), re.IGNORECASE | re.DOTALL)
        if create_project_match:
            log_system_message(f"[Communication] Quick command: Creating project with create_project_match")
            _, project_id, objective = create_project_match.groups()
            plan_summary = self.brain.initiate_project_planning(project_id.strip(), objective.strip())
            return plan_summary
        
        # Command: Generate tasks for an existing project
        gen_tasks_match = re.match(r"^(generate|create|make)\s+tasks\s+(?:for|on)\s+([\w-]+)$", message.strip(), re.IGNORECASE)
        if gen_tasks_match:
            log_system_message(f"[Communication] Quick command: Generating tasks for plan with gen_tasks_match")
            project_id = gen_tasks_match.group(2).strip()
            # Check if project exists in Brain
            if project_id not in self.brain.projects:
                log_warning(f"[Communication] Project '{project_id}' does not exist.")
                return f"Project '{project_id}' does not exist. Please create it first with 'plan {project_id}=<objective>'."
            
            # Get project steps and participants from Brain
            steps = self.brain.projects[project_id].get("plan_steps", [])
            participants = list(self.brain.projects[project_id].get("participants", set()))
            
            if not steps:
                log_warning(f"[Communication] Project '{project_id}' has no steps defined.")
                return f"Project '{project_id}' has no steps defined. Please create a plan first."
            
            # Generate tasks based on the project plan
            self.brain.generate_tasks_from_plan(project_id, steps, participants)
            return f"Tasks generated for project '{project_id}'."
        
        # Command: Add participant to project
        add_participant_match = re.match(r"^add\s+([\w\s-]+)\s+to\s+project\s+([\w-]+)$", message.strip(), re.IGNORECASE)
        if add_participant_match:
            log_system_message(f"[Communication] Quick command: Adding participant to project")
            participant_name, project_id = add_participant_match.groups()
            participant_name = participant_name.strip()
            project_id = project_id.strip()
            
            # Call the Brain method to add participant
            return self.brain.add_participant_to_project(project_id, participant_name)
        
        # Command: Finalize project planning and generate tasks
        finalize_project_match = re.match(r"^(confirm participants for|finalize)\s+project\s+([\w-]+)$", message.strip(), re.IGNORECASE)
        if finalize_project_match:
            log_system_message(f"[Communication] Quick command: Finalizing project")
            project_id = finalize_project_match.group(2).strip()
            return self.brain.finalize_and_plan_project(project_id)

        return None

    def _chat_with_llm(self, message: str) -> str:
        """
        Fallback handler for general conversation with the LLM.

        Appends the user message and LLM response to conversation history.

        Args:
            message (str): The user's message.

        Returns:
            str: The LLM's response.
        """
        # Add user's message to the conversation history
        self.conversation_history.append({'role':'user','content':message})
        
        # Query the LLM with the updated conversation history
        response = self.brain.query_llm(self.conversation_history)
        
        # Add LLM's response to the conversation history
        self.conversation_history.append({'role':'assistant','content':response})
        
        return response

    def _handle_email_composition(self, intent: dict, message: str) -> Optional[str]:
        """
        Manages interactive email composition.

        Prompts for missing information (recipient, subject, body) or confirms
        the draft if all details are present. Requires Brain and Gmail services.
        Note: Actual email sending is not implemented.

        Args:
            intent (dict): Parsed intent for sending an email, including potential
                           'missing_info', 'recipient', 'subject', 'body'.
            message (str): The original user message (for context).

        Returns:
            Optional[str]: A message to the user (prompt or confirmation), or an error.
        """
        # Check for availability of essential services (Brain and Gmail)
        if not self.brain or not self.gmail_service:
            return "Email services are not available."
            
        # Check if any information is missing for the email
        missing = intent.get('missing_info', [])
        if missing:
            # Prompt the user for the missing information
            return f"Okay, let's draft an email. I still need the following: {', '.join(missing)}."
        else:
            # All information is present, prepare a draft confirmation
            recipient = intent.get('recipient', 'unknown') # Default if somehow still missing
            subject = intent.get('subject', 'no subject') # Default if somehow still missing
            body = intent.get('body', 'empty body')       # Default if somehow still missing
            # TODO: Implement actual email sending functionality
            return f"Drafting email to {recipient} with subject '{subject}'. Ready to send? (Send command not implemented yet)"

    def _handle_email(self, intent: dict, message: str) -> Optional[str]:
        """
        Routes email-related intents. (DEPRECATED)

        Delegates to `_handle_email_composition` for sending emails or to
        `brain.process_advanced_email_command` for other email actions.
        This method's logic may be superseded by `receive_message`.

        Args:
            intent (dict): Parsed email intent, with 'is_send_email' and 'action' keys.
            message (str): The original user message (for context).

        Returns:
            Optional[str]: Response from email handling or a generic/error message.
        """
        # Check if the Brain (core logic) is available
        if not self.brain:
            return "Email processing is not available."
            
        # Check if the intent is to send/compose an email
        if intent.get('is_send_email', False):
            return self._handle_email_composition(intent, message)
        else:
            # Handle other email actions (e.g., search, list labels)
            action = intent.get('action')
            if action and action != 'none': # Ensure there is a valid action
                # Delegate to the brain to process advanced email commands
                # Note: The 'intent' dict itself is passed here, which might be specific
                # to how process_advanced_email_command expects its input.
                resp = self.brain.process_advanced_email_command(intent)
                return resp
            else:
                # Log if the email intent is unhandled or unclear
                log_warning(f"Unhandled email intent in _handle_email: {intent}")
                return "I understand you want to do something with email, but I'm not sure exactly what."
