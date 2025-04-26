import re
import base64
from typing import List, Dict, Optional

from secretary.utilities.logging import log_user_message, log_network_message
from secretary.utilities.google import initialize_google_services
from secretary.scheduler import Scheduler
# from secretary.brain import Brain

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
        """
        self.node_id = node_id
        self.llm = llm_client
        self.network = network
        self.open_api_key = open_api_key

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
            sender_id (str): Who sent the message (e.g. 'cli_user' or a node ID).
            
        Returns:
            Optional[str]: The textual response to be sent back, or None if handled internally.
        """
        
        # Log the message
        if sender_id == 'cli_user':
            log_user_message(sender_id, message)
        else:
            log_network_message(sender_id, self.node_id, message)
        print(f"[{self.node_id}] Received from {sender_id}: {message}")

        # quick CLI command handling
        quick_cmd_response = self._handle_quick_command(message, sender_id)
        if quick_cmd_response is not None:
            return quick_cmd_response

        # Calendar commands -> delegate entirely to Scheduler
        # --- Temporarily commented out until Scheduler is implemented ---
        # cal_intent = self.scheduler._detect_calendar_intent(message)
        # if cal_intent.get('is_calendar_command', False):
        #     return self.scheduler.handle_calendar(cal_intent, message)

        # Email commands - only check if message looks like an email-related command
        # Simple heuristic to avoid unnecessary LLM calls for non-email messages
        email_keywords = ["email", "gmail", "mail", "inbox", "message", "send", "write", "compose", "draft"]
        if any(keyword in message.lower() for keyword in email_keywords):
            # First, check for advanced commands (like search, list labels) which should return a response
            adv_email_analysis = self.brain._analyze_email_command(message)
            if adv_email_analysis.get('action') in ['list_labels', 'advanced_search', 'fetch_recent', 'search']:
                return self.brain.process_advanced_email_command(adv_email_analysis)
                
            # Then, check for send email intent
            send_email_intent = self.brain._detect_send_email_intent(message)
            if send_email_intent.get('is_send_email', False):
                # Email composition might be multi-turn, handle appropriately
                # This might need further refinement depending on how email composition flow works
                return self._handle_email_composition(send_email_intent, message)

        # Fallback: send to LLM
        return self._chat_with_llm(message)

    def _handle_quick_command(self, message: str, sender_id: str) -> Optional[str]:
        """
        Single-turn commands from CLI: 'tasks' and 'plan <project>=<objective>'.

        Returns: 
            Optional[str]: Response string if command handled, None otherwise.
        """
        if sender_id != 'cli_user':
            return None
        cmd = message.strip().lower()
        if cmd == 'tasks':
            tasks_list = self.brain.list_tasks()
            return tasks_list
        match = re.match(r"^plan\s+([\w-]+)\s*=\s*(.+)$", message.strip(), re.IGNORECASE)
        if match:
            project_id, objective = match.groups()
            plan_summary = self.brain.plan_project(project_id.strip(), objective.strip())
            return plan_summary
        return None

    def _chat_with_llm(self, message: str) -> str:
        """
        Fallback: append to history, query LLM, print and return the response.
        """
        self.conversation_history.append({'role':'user','content':message})
        response = self.brain.query_llm(self.conversation_history)
        self.conversation_history.append({'role':'assistant','content':response})
        return response

    def _handle_email_composition(self, intent: dict, message: str) -> Optional[str]:
        """Handles the process of composing and sending an email."""
        missing = intent.get('missing_info', [])
        if missing:
            return f"Okay, let's draft an email. I still need the following: {', '.join(missing)}."
        else:
            recipient = intent.get('recipient', 'unknown')
            subject = intent.get('subject', 'no subject')
            body = intent.get('body', 'empty body')
            return f"Drafting email to {recipient} with subject '{subject}'. Ready to send? (Send command not implemented yet)"

    def _handle_email(self, intent: dict, message: str) -> Optional[str]:
        """
        Handle both simple send-email intents and advanced email commands.
        DEPRECATED? receive_message now routes based on intent analysis.
        """
        if intent.get('is_send_email', False):
            return self._handle_email_composition(intent, message)
        else:
            action = intent.get('action')
            if action and action != 'none':
                resp = self.brain.process_advanced_email_command(intent)
                return resp
            else:
                log_warning(f"Unhandled email intent in _handle_email: {intent}")
                return "I understand you want to do something with email, but I'm not sure exactly what."
