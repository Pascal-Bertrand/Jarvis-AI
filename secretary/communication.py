import re
import base64
from typing import List, Dict, Optional

from secretary.utilities.logging import log_user_message, log_network_message
from secretary.utilities.google import initialize_google_services
from secretary.scheduler import Scheduler
from secretary.brain import Brain

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

        # Initialize Google services
        services = initialize_google_services(self.node_id)
        self.calendar_service = services.get('calendar')
        self.gmail_service = services.get('gmail')

        # Scheduler handles all calendar logic
        self.scheduler = Scheduler(self.node_id, self.calendar_service)

        # Brain handles all other logic
        self.brain = Brain(self.node_id, self.open_api_key, self.network, llm_params=None, socketio_instance=None)

    def receive_message(self, message: str, sender_id: str):
        """
        Process an incoming message in four steps:
          1) Quick CLI commands
          2) Calendar commands (delegated to Scheduler)
          3) Email commands
          4) Fallback chat via LLM

        Args:
            message (str): The incoming message text.
            sender_id (str): Who sent the message (e.g. 'cli_user' or a node ID).
        """
        
        # Log the message
        if sender_id == 'cli_user':
            log_user_message(sender_id, message)
        else:
            log_network_message(sender_id, self.node_id, message)
        print(f"[{self.node_id}] Received from {sender_id}: {message}")

        # quick CLI command handling
        if self._handle_quick_command(message, sender_id):
            return

        # Calendar commands -> delegate entirely to Scheduler
        cal_intent = self.scheduler._detect_calendar_intent(message)
        if cal_intent.get('is_calendar_command', False):
            return self.scheduler.handle_calendar(cal_intent, message)

        # Email commands
        email_intent = self.brain._detect_send_email_intent(message)
        if email_intent.get('is_send_email', False) or email_intent.get('action', 'none') != 'none':
            return self._handle_email(email_intent, message)

        # Fallback: send to LLM
        return self._chat_with_llm(message)

    def _handle_quick_command(self, message: str, sender_id: str) -> bool:
        """
        Single-turn commands from CLI: 'tasks' and 'plan <project>=<objective>'.

        Returns True if processed.
        """
        if sender_id != 'cli_user':
            return False
        cmd = message.strip().lower()
        if cmd == 'tasks':
            tasks_list = self.brain.list_tasks()
            print(f"[{self.node_id}] Response: {tasks_list}")
            return True
        match = re.match(r"^plan\s+([\w-]+)\s*=\s*(.+)$", message.strip(), re.IGNORECASE)
        if match:
            project_id, objective = match.groups()
            self.brain.plan_project(project_id.strip(), objective.strip())
            return True
        return False

    def _chat_with_llm(self, message: str):
        """
        Fallback: append to history, query LLM, print and return the response.
        """
        self.conversation_history.append({'role':'user','content':message})
        response = self.brain.query_llm(self.conversation_history)
        self.conversation_history.append({'role':'assistant','content':response})
        print(f"[{self.node_id}] Response: {response}")
        return response

    def _handle_email(self, intent: dict, message: str):
        """
        Handle both simple send-email intents and advanced email commands.
        """
        if intent.get('is_send_email', False):
            missing = intent.get('missing_info', [])
            self._start_email_composition(message, missing, intent)
        else:
            action = intent.get('action')
            if action and action != 'none':
                resp = self.brain.process_advanced_email_command(message)
                print(f"[{self.node_id}] Response: {resp}")

    def fetch_emails(self, max_results=10, query=None):
        """
        Fetch emails from the Gmail account using the Gmail service.
        
        Args:
            max_results (int): Maximum number of emails to fetch.
            query (str, optional): A search query to filter the emails.
        
        Returns:
            list: A list of emails with details like subject, sender, date, snippet, and body.
        """
        
        if not self.gmail_service:
            print(f"[{self.node_id}] Gmail service not available")
            return []
        
        try:
            # Default query to get recent emails
            query_string = query if query else ""
            
            # Get list of messages matching the query
            results = self.gmail_service.users().messages().list(
                userId='me',
                q=query_string,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                print(f"[{self.node_id}] No emails found matching query: {query_string}")
                return []
            
            # Fetch full details for each message
            emails = []
            for message in messages:
                msg_id = message['id']
                msg = self.gmail_service.users().messages().get(
                    userId='me', 
                    id=msg_id, 
                    format='full'
                ).execute()
                
                # Extract header information
                headers = msg['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No subject)')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown sender)')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                
                # Extract body content
                body = self._extract_email_body(msg['payload'])
                
                # Add email data to list
                emails.append({
                    'id': msg_id,
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'body': body,
                    'snippet': msg.get('snippet', ''),
                    'labelIds': msg.get('labelIds', [])
                })
            
            print(f"[{self.node_id}] Fetched {len(emails)} emails")
            return emails
        
        except Exception as e:
            print(f"[{self.node_id}] Error fetching emails: {str(e)}")
            return []
    
    def _extract_email_body(self, payload):
        """
        Recursively extract the email body text from the Gmail message payload.
        
        Handles both single-part and multipart messages by performing base64 decoding.
        
        Args:
            payload (dict): The payload section of a Gmail message.
        
        Returns:
            str: Decoded text content of the email, or a placeholder if not found.
        """
        
        if 'body' in payload and payload['body'].get('data'):
            # Base64 decode the body
            body_data = payload['body']['data']
            body_bytes = base64.urlsafe_b64decode(body_data)
            return body_bytes.decode('utf-8')
        
        # If the payload has parts (multipart email), recursively extract from parts
        if 'parts' in payload:
            text_parts = []
            for part in payload['parts']:
                # Focus on text/plain parts first, fall back to HTML if needed
                if part['mimeType'] == 'text/plain':
                    text_parts.append(self._extract_email_body(part))
                elif part['mimeType'] == 'text/html' and not text_parts:
                    text_parts.append(self._extract_email_body(part))
                elif part['mimeType'].startswith('multipart/'):
                    text_parts.append(self._extract_email_body(part))
            
            return '\n'.join(text_parts)
        
        return "(No content)"
