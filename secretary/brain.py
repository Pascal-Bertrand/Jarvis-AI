import re, json
from datetime import datetime, timedelta
import openai
import threading

from network.internal_communication import Intercom
from network.tasks import Task
from network.people import People
from secretary.utilities.logging import (
    log_user_message, log_agent_message,
    log_system_message, log_network_message,
    log_error, log_warning,
    log_api_request, log_api_response
)
from secretary.socketio_ext import socketio
from config.agents import AGENT_CONFIG


class LLMClient:
    """
    A thin wrapper around OpenAI for consistent logging and system-prompt injection.
    """

    def __init__(self, api_key: str, params: dict):
        """
        Args:
            api_key: Your OpenAI API key.
            params: Dict containing 'model', 'temperature', 'max_tokens', etc.
        """
        openai.api_key = api_key
        self.client = openai
        self.params = params

    def chat(self, messages):
        """
        Sends a chat completion request, with a fixed system prompt
        and logs both request and response.
        """
        
        system = [{
            "role": "system",
            "content": (
                "You are a direct and concise AI agent for an organization. "
                "Provide short, to-the-point answers and do not continue repeating Goodbyes."
            )
        }]
        prompt = system + messages
        try:
            log_api_request("openai_chat", {"model": self.params["model"], "messages": prompt})
            resp = self.client.chat.completions.create(
                model=self.params["model"],
                messages=prompt,
                temperature=self.params["temperature"],
                max_tokens=self.params["max_tokens"]
            )
            text = resp.choices[0].message.content.strip()
            log_api_response("openai_chat", {"response": text})
            return text
        
        except Exception as e:
            log_error(f"LLMClient.chat failed: {e}")
            return "LLM query failed."
        
class Confirmation:
    """
    Simple interactive yes/no prompt. Returns True on 'y' answers.
    
    Can be instantiated anywhere to manage confirmation flows.
    """

    def __init__(self):
        """
        Initialize the Confirmation service.
        (Future configuration hooks can go here.)
        """
        self.socketio = socketio  # Assuming socketio is globally available
        # no state for now, but __init__ makes this class instantiable externally
        pass

    def request(self, prompt: str) -> bool:
        """
        Prompt the user in console and return True if the answer starts with 'y'.
        
        Args:
            prompt (str): The question to display to the user.
        
        Returns:
            bool: True if the user's response begins with 'y' (case-insensitive).
        """

        answer = prompt.strip().lower()
        return answer.startswith("y")

class Brain:
    """
    The core orchestrator of the secretary's logic.

    Responsibilities:
      - Supervises all procedures (reasoning) and advanced LLM workflows.
      - Delegates node registration and messaging to the Intercom network.
      - Manages projects, tasks, and calendar interactions, awaiting user confirmation before taking major actions.
    """

    def __init__(
        self,
        node_id: str,
        openai_api_key: str,
        network: Intercom,
        llm_params: dict = None,
        socketio_instance=None
    ):
        self.node_id = node_id

        # --- LLM client setup ---
        openai.api_key = openai_api_key
        self.client = openai
        self.llm_params = llm_params or {
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "max_tokens": 1000
        }

        # wraps logging / system prompt injection centrally
        self.llm = LLMClient(openai_api_key, self.llm_params)

        # User confirmation service
        self.confirmation = Confirmation()

        # --- Network / messaging / tasks ---
        self.network = network
        self.network.register_node(node_id, self)
        self.tasks = []            # local cache if needed
        self.projects = {}         # project plans by project_id

        # This will be used to track the state of the meeting scheduling process (temporarily until memory.py is implemented)
        self.meeting_context = {
            'active': False,
            'initial_message': None,
            'missing_info': [],
            'collected_info': {}
        }

        self.people = People()     # local cache of people (if needed)
        self.calendar = []
        # self.calendar = [{
        #         'project_id': None,
        #         'start_time': None,
        #         'end_time': None,
        #         'participants': None,
        #         'meeting_info': None,
        #         'event_id': None
        #     }]
        self.context = []       # conversation history for LLM (if needed)
        self.scheduler = None
        self.confirmation_context = {
            'active': False,
            'context': None,      # e.g. "schedule meeting", "cancel meeting"
            'initial_message': None,
            'start_datetime': None,
            'end_datetime': None
        }

        # --- Calendar & Email stubs (to be injected or initialized elsewhere) ---
        self.calendar_service = None
        self.gmail_service    = None

        # --- SocketIO (if using realtime UI updates) ---
        self.socketio = socketio_instance

        log_system_message(f"[Brain:{self.node_id}] initialized.")
        
    def _detect_calendar_intent(self, message):
        """
        Detect if the incoming message is related to calendar commands.
        
        The method constructs a prompt asking the LLM to analyze if the message is calendar related,
        and what action is intended (e.g., scheduling, cancellation).
        
        Args:
            message (str): The message to analyze.
        
        Returns:
            dict: A JSON object that includes:
                  - is_calendar_command (bool)
                  - action (string: "schedule_meeting", "cancel_meeting", "list_meetings", "reschedule_meeting", or None)
                  - missing_info (list of strings indicating any missing information)
        """
        
        prompt = f"""
        Analyze this message and determine if it's a calendar-related command: '{message}'
        Return JSON with:
        - is_calendar_command: boolean
        - action: string ("schedule_meeting", "cancel_meeting", "list_meetings", "reschedule_meeting", or null)
        - missing_info: array of strings (what information is missing: "time", "duration", "participants", "date", "title")
        """
        
        try:
            # 1) Ask the LLM via your wrapper so you get back plain text
            raw = self.query_llm([{"role": "user", "content": prompt}])

            # 2) Strip out ```json fences if present
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
            json_text = m.group(1) if m else raw.strip()

            # 3) Parse it
            data = json.loads(json_text)

            # Validate & fill defaults
            return {
                "is_calendar_command": bool(data.get("is_calendar_command")),
                "action": data.get("action"),
                "missing_info": data.get("missing_info", []) or []
            }
        
        except Exception as e:
            print(f"[{self.node_id}] Error detecting intent: {str(e)}")
            return {"is_calendar_command": False, "action": None, "missing_info": []}


    def _extract_meeting_details(self, message):
        """
        Extract detailed meeting information from the given message using LLM assistance.
        
        The function sends a prompt to the LLM to parse the meeting details and returns a structured JSON
        with keys like title, participants, date, time, and duration.
        
        Args:
            message (str): The input meeting instruction message.
        
        Returns:
            dict: A dictionary with meeting details. Missing date/time fields are substituted with defaults.
        """
        
        prompt = f"""
        Extract complete meeting details from:'{message}'
        
        Return JSON with:
        - title: meeting title
        - participants: array of participants (use only: ceo, marketing, engineering, design)
        - date: meeting date (YYYY-MM-DD format, leave empty to use current date)
        - time: meeting time (HH:MM format, leave empty to use current time + 1 hour)
        - duration: duration in minutes (default 60)
        
        If any information is missing, leave the field empty (don't guess).
        """
        
        try:
            # Call through LLMClient
            raw = self.llm.chat([{"role": "user", "content": prompt}])
            result = json.loads(raw)
            
            # Set defaults if date or time are missing
            if not result.get("date"):
                result["date"] = datetime.now().strftime("%Y-%m-%d")
            
            # Use current time + 1 hour if not specified
            if not result.get("time"):
                result["time"] = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
            
            return result
        except Exception as e:
            print(f"[{self.node_id}] Error extracting meeting details: {str(e)}")
            return {}
        
    def query_llm(self, messages):
        """
        Query the language model with a list of messages.
        
        A system prompt is prepended to guide the LLM to be short and concise.
        
        Args:
            messages (list): A list of message dictionaries (role and content).
        
        Returns:
            str: The trimmed text response from the LLM.
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
            # Log the API request
            log_api_request("openai_chat", {"model": self.llm_params["model"], "messages": combined_messages})
            
            # Call through LLMClient
            response_content = self.llm.chat(combined_messages)
            
            # Log the agent's response
            log_agent_message(self.node_id, response_content)
            
            return response_content
        
        except Exception as e:
            error_msg = f"LLM query failed: {e}"
            print(f"[{self.node_id}] {error_msg}")
            log_error(error_msg)
            return "LLM query failed."
        
    def plan_project(self, project_id: str, objective: str):
        """
        Create a detailed project plan using the LLM.
        
        This method sends the project objective to the LLM to generate a plan in JSON format, parses
        the resulting plan for stakeholders and steps, writes the plan to a file, and schedules a meeting.
        
        Args:
            project_id (str): The identifier for the project.
            objective (str): The objective or goal of the project.
        """
        
        log_system_message(f"[Brain] [{self.node_id}] Planning project '{project_id}' with objective: {objective}")
        
        if project_id not in self.projects:
            self.projects[project_id] = {
                "name": "Project " + project_id,
                "plan": [],
                "participants": set()
            }

        roles = list({agent["id"].lower() for agent in AGENT_CONFIG})

        plan_prompt = f"""
        You are creating a detailed project plan for project '{project_id}'.
        Objective: {objective}

        The plan should include:
        1. All stakeholders involved in the project. Use only these roles: {roles}.
        2. Detailed steps needed to execute the plan, including time and cost estimates.
        Each step should be written in bullet points (with correct spacing) and full sentences.

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

        # --- Start: Extract JSON from potential markdown fences ---
        json_to_parse = response.strip()
        match = re.search(r"```json\n(.+)\n```", json_to_parse, re.DOTALL | re.IGNORECASE)
        if match:
            json_to_parse = match.group(1).strip()
        else:
            # If the response appears to be plain JSON without fences, use it as is.
            if json_to_parse.startswith("{") and json_to_parse.endswith("}"):
                pass # Assume it's already JSON
            else:
                # If no fences and doesn't look like JSON, it's likely an error message
                log_error(f"[Brain] [{self.node_id}] LLM response doesn't appear to be JSON: {json_to_parse}")
                return "Could not generate project plan. The AI's response was not in the expected format."
        # --- End: Extract JSON ---

        try:
            log_system_message(f"[Brain] [{self.node_id}] Starting project extraction for '{project_id}'")
            # Attempt to parse the extracted JSON response
            data = json.loads(json_to_parse) 
            stakeholders = data.get("stakeholders", [])
            steps = data.get("steps", [])
            self.projects[project_id]["plan"] = steps

            # --- Start: Format and print plan details for UI response ---
            plan_summary = f"Project '{project_id}' plan created:\n"
            plan_summary += f"Stakeholders: {', '.join(stakeholders)}\n"
            plan_summary += "Steps:\n"
            for i, step in enumerate(steps, 1):
                plan_summary += f"  {i}. {step.get('description', 'No description')}\n"
            # Print the summary which will be captured as the response
            # print(f"[{self.node_id}] Response: {plan_summary.strip()}") # Remove print
            # --- End: Format and print plan details ---

            # Save the project plan to a text file
            with open(f"{project_id}_plan.txt", "w", encoding="utf-8") as file:
                file.write(f"Project ID: {project_id}\n")
                file.write(f"Objective: {objective}\n")
                file.write("Stakeholders:\n")
                for stakeholder in stakeholders:
                    file.write(f"  - {stakeholder}\n")
                file.write("Steps:\n")
                for step in steps:
                    file.write(f"  - {step.get('description', '')}\n")

            participants = []
            # 'roles' is a list of lowercased agent IDs, e.g., ['ceo', 'marketing', 'engineering']
            for stakeholder_from_llm in stakeholders: # e.g. "The CEO", "Marketing Team"
                # Normalize the stakeholder name from LLM (lowercase and remove extra spaces)
                normalized_stakeholder_name = stakeholder_from_llm.lower().strip() # e.g. "the ceo", "marketing team"
                
                matched_agent_id = None
                # Iterate through each configured agent ID
                for agent_id in roles: # agent_id is e.g. 'ceo', 'marketing'
                    # Check if the agent_id is a substring of the normalized stakeholder name
                    if agent_id in normalized_stakeholder_name: # e.g. 'ceo' in 'the ceo'
                        matched_agent_id = agent_id # The agent_id itself is what we need
                        break # Found a match, no need to check other agent_ids for this stakeholder
                
                if matched_agent_id:
                    participants.append(matched_agent_id)
                    self.projects[project_id]["participants"].add(matched_agent_id)
                else:
                    print(f"[{self.node_id}] No mapping for stakeholder '{stakeholder_from_llm}'. Skipping.")

            print(f"[{self.node_id}] Project participants: {participants}")
            #TODO
            # Schedule a meeting if valid participants were identified
            #if participants:
            #    self.schedule_meeting(project_id, participants)
            #else:
            #    print(f"[{self.node_id}] No valid participants identified for project '{project_id}'. Skipping meeting schedule.")
            
            # Generate tasks based on the plan
            self.generate_tasks_from_plan(project_id, steps, participants)

            # Emit update events (assuming a global socketio object)
            print(f"[{self.node_id}] Emitting update events for UI.")
            # Make sure socketio is accessible here. Assuming it's global for simplicity.
            socketio.emit('update_projects') 
            socketio.emit('update_tasks')
            
            log_system_message(f"[Brain] [{self.node_id}] Project '{project_id}' plan created successfully.")
            
            return plan_summary.strip() # Return the summary
            
        except json.JSONDecodeError as e:
            # Handle JSON parsing failure
            print(f"[{self.node_id}] Failed to parse JSON plan: {e}")
            print(f"[{self.node_id}] Received non-JSON response from LLM: {response}")
            # Inform the user via the response mechanism
            # print(f"[{self.node_id}] Response: Could not generate project plan. The AI's response was not in the expected format.")
            # return # Stop processing the plan if JSON is invalid
            return "Could not generate project plan. The AI's response was not in the expected format." # Return error message

    def generate_tasks_from_plan(self, project_id: str, steps: list, participants: list):
        """
        Generate tasks from a project plan by creating task objects using LLM-assisted function calling.
        
        For each step in the plan, this method constructs a prompt to generate 1-3 tasks, calls the LLM with a
        function tool specification (create_task), parses the returned task details, and creates the Task objects.
        
        Args:
            project_id (str): Identifier for the project.
            steps (list): List of steps from the project plan.
            participants (list): List of node identifiers who are the project participants.
        """
        
        log_system_message(f"[Brain] [{self.node_id}] Generating tasks for project '{project_id}'")
        
        # Create a string representation of participants for the tool description
        # participants is a list like ['ceo', 'engineering']
        participant_roles_str = ", ".join(participants) if participants else "any relevant project role"

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
                                "description": f"Role responsible for this task. Assign to one or more of the project participants: {participant_roles_str}. These are the available roles from the project plan."
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
        
        # Process each project plan step
        for i, step in enumerate(steps):
            step_description = step.get("description", "")
            
            log_system_message(f"[Brain] [{self.node_id}] Generating tasks for step {i+1}: {step_description}")
            


            # Refined prompt to be very clear about using the provided participants
            current_participants_list_str = ", ".join(participants) if participants else "the designated project roles"
            prompt = f"""
            For project '{project_id}', analyze this step: "{step_description}"
            
            Based on this step, create 1 to 3 specific tasks.
            
            The project participants for assigning these tasks are: {current_participants_list_str}.
            Each task MUST be assigned to one or more of these participants. Do not assign tasks to roles not in this list.
            """
            
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    tools=functions,
                    tool_choice={"type": "function", "function": {"name": "create_task"}}
                )
                
                # Process any function calls in the response to create tasks
                for choice in response.choices:
                    if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                        for tool_call in choice.message.tool_calls:
                            if tool_call.function.name == "create_task":
                                task_data = json.loads(tool_call.function.arguments)
                                
                                # Create a new Task using the provided data
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
                                    
                                    # Create a calendar reminder for the task
                                    return self.scheduler.create_calendar_reminder(task)
            
            except Exception as e:
                print(f"[{self.node_id}] Error generating tasks for step {i+1}: {e}")

    def list_tasks(self):
        """
        List all tasks assigned to this node.
        
        Retrieves tasks for this node from the network and formats a string summary.
        
        Returns:
            str: A formatted string of tasks with their titles, due dates, priority, and descriptions.
        """
        
        log_system_message(f"[Brain] Entered task-listing for {self.node_id}.")
        
        if not self.network:
            log_warning(f"[Brain] [{self.node_id}] No network connected for task listing.")
            return "No network connected."
            
        tasks = self.network.get_tasks_for_node(self.node_id)
        if not tasks:
            log_warning(f"[Brain] [{self.node_id}] No tasks found for this node.")
            return f"No tasks assigned to {self.node_id}."
            
        result = f"Tasks for {self.node_id}:\n"
        log_system_message(f"[Brain] [{self.node_id}] Found {len(tasks)} tasks.")
        for i, task in enumerate(tasks, 1):
            result += f"{i}. {task.title} (Due: {task.due_date.strftime('%Y-%m-%d')}, Priority: {task.priority})\n"
            result += f"   Description: {task.description}\n"
            log_system_message(f"[Brain] [{self.node_id}] Task {i}: {task.title} (Due: {task.due_date.strftime('%Y-%m-%d')}, Priority: {task.priority})")
            
        return result

    def summarize_emails(self, emails, summary_type="concise"):
        """
        Summarize a list of emails using the LLM.
        
        Constructs a prompt by concatenating email details and requests either a concise or detailed summary.
        
        Args:
            emails (list): List of email dictionaries.
            summary_type (str): "concise" or "detailed" summary preference.
        
        Returns:
            str: The summary produced by the LLM.
        """
        
        if not emails:
            return "No emails to summarize."
        
        # Prepare the email data for the LLM
        email_texts = []
        for i, email in enumerate(emails, 1):
            email_texts.append(
                f"Email {i}:\n"
                f"From: {email['sender']}\n"
                f"Subject: {email['subject']}\n"
                f"Date: {email['date']}\n"
                f"Snippet: {email['snippet']}\n"
            )
        
        emails_content = "\n\n".join(email_texts)
        
        # Choose prompt based on summary type
        if summary_type == "detailed":
            prompt = f"""
            Please provide a detailed summary of the following emails:
            {emails_content}
            
            For each email, include:
            1. The sender
            2. The subject
            3. Key points from the email
            4. Any action items or important deadlines
            """
        else:
            # Default to concise summary
            prompt = f"""
            Please provide a concise summary of the following emails:
            {emails_content}
            
            Keep your summary brief and focus on the most important information.
            """
        
        # Get summary from the LLM
        response = self.query_llm([{"role": "user", "content": prompt}])
        return response

    def process_email_command(self, command):
        """
        Process a natural language command related to emails.
        
        Detects the intent (e.g., fetch recent, search) and calls the appropriate email processing method.
        
        Args:
            command (str): The email command in natural language.
        
        Returns:
            str: The result or summary of the email action.
        """
        
        # First, detect the intent of the email command
        intent = self._detect_email_intent(command)
        
        action = intent.get("action")
        
        if action == "fetch_recent":
            # Get recent emails
            count = intent.get("count", 5)
            emails = self.fetch_emails(max_results=count)
            if not emails:
                return "I couldn't find any recent emails."
            
            summary_type = intent.get("summary_type", "concise")
            return self.summarize_emails(emails, summary_type)
            
        elif action == "search":
            # Search emails with query
            query = intent.get("query", "")
            count = intent.get("count", 5)
            
            if not query:
                return "I need a search query to find emails. Please specify what you're looking for."
            
            emails = self.fetch_emails(max_results=count, query=query)
            if not emails:
                return f"I couldn't find any emails matching '{query}'."
            
            summary_type = intent.get("summary_type", "concise")
            return self.summarize_emails(emails, summary_type)
            
        else:
            return "I'm not sure what you want to do with your emails. Try asking for recent emails or searching for specific emails."

    def _detect_email_intent(self, message):
        """
        Detect the intent of an email-related command using LLM-based analysis.
        
        Constructs a prompt asking the LLM to output a JSON object with fields indicating:
          - The action ("fetch_recent", "search", or "none")
          - Count (number of emails to fetch)
          - Query (if searching)
          - Summary type ("concise" or "detailed")
        
        Args:
            message (str): The email command to analyze.
        
        Returns:
            dict: Parsed JSON object with detected intent details.
        """
        
        prompt = f"""
        Analyze this message and determine what email action is being requested:
        '{message}'
        
        Return JSON with these fields:
        - action: string ("fetch_recent", "search", "none")
        - count: integer (number of emails to fetch/search, default 5)
        - query: string (search query if applicable)
        - summary_type: string ("concise" or "detailed")
        
        Only extract information explicitly mentioned in the message.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[{self.node_id}] Error detecting email intent: {str(e)}")
            # Default fallback
            return {"action": "none", "count": 5, "query": "", "summary_type": "concise"}
        
            # --- Email Fetching & Processing Methods (Moved from Communication) ---

    def fetch_emails(self, max_results=10, query=None):
        """
        Fetch emails from the Gmail account using the Gmail service.

        Args:
            max_results (int): Maximum number of emails to fetch.
            query (str, optional): A search query to filter the emails.

        Returns:
            list: A list of emails with details like subject, sender, date, snippet, and body.
        """
        import base64 # Make sure base64 is available
        from secretary.utilities.logging import log_warning, log_error, log_system_message, log_api_request, log_api_response

        if not self.gmail_service:
            log_warning(f"[{self.node_id}] Gmail service not available for fetch_emails")
            return []

        try:
            # Default query to get recent emails
            query_string = query if query else ""
            log_api_request("gmail_list", {"userId": 'me', "q": query_string, "maxResults": max_results})

            # Get list of messages matching the query
            results = self.gmail_service.users().messages().list(
                userId='me',
                q=query_string,
                maxResults=max_results
            ).execute()
            log_api_response("gmail_list", results)

            messages = results.get('messages', [])

            if not messages:
                log_system_message(f"[{self.node_id}] No emails found matching query: {query_string}")
                return []

            # Fetch full details for each message
            emails = []
            for message in messages:
                msg_id = message['id']
                log_api_request("gmail_get", {"userId": 'me', "id": msg_id, "format": 'full'})
                try:
                    msg = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg_id,
                        format='full' # 'metadata' is faster if only headers/snippet needed initially
                    ).execute()
                    log_api_response("gmail_get", {"id": msg_id, "snippet": msg.get('snippet', '')})

                    # Extract header information
                    headers = msg.get('payload', {}).get('headers', [])
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No subject)')
                    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), '(Unknown sender)')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

                    # Extract body content
                    body = self._extract_email_body(msg.get('payload', {}))

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
                except Exception as get_err:
                     log_error(f"[{self.node_id}] Error getting details for email ID {msg_id}: {get_err}")
                     continue # Skip this email if details can't be fetched

            log_system_message(f"[{self.node_id}] Fetched {len(emails)} emails")
            return emails

        except Exception as e:
            log_error(f"[{self.node_id}] Error fetching emails: {str(e)}")
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
        import base64 # Ensure base64 is imported here if not globally
        from secretary.utilities.logging import log_warning, log_error # Ensure correct logging functions are available

        if not payload:
             return "(No payload)"

        mime_type = payload.get('mimeType', '')

        if 'body' in payload and payload['body'].get('size', 0) > 0:
            body_data = payload['body'].get('data')
            if body_data:
                try:
                    body_bytes = base64.urlsafe_b64decode(body_data)
                    # Decode based on mimeType if possible, otherwise default to utf-8
                    charset = 'utf-8' # Default
                    # Look for charset in headers if available (might be in part headers)
                    part_headers = payload.get('headers', [])
                    content_type_header = next((h['value'] for h in part_headers if h['name'].lower() == 'content-type'), None)
                    if content_type_header and 'charset=' in content_type_header:
                        charset = content_type_header.split('charset=')[-1].split(';')[0].strip().lower()

                    try:
                         # Attempt decoding with detected/default charset
                         decoded_body = body_bytes.decode(charset, errors='replace')
                         # Return only if it's a text type, otherwise indicate non-text
                         if mime_type.startswith('text/'):
                              return decoded_body
                         else:
                              return f"(Non-text content: {mime_type})"
                    except LookupError: # Handle unknown encoding
                         log_warning(f"Unknown charset '{charset}', falling back to utf-8 with replace.")
                         return body_bytes.decode('utf-8', errors='replace') # Fallback

                except (base64.binascii.Error, ValueError, TypeError) as e:
                    log_warning(f"Error decoding email body part (mime: {mime_type}): {e}")
                    return "(Error decoding content)"

        # If the payload has parts (multipart email), recursively extract from parts
        if 'parts' in payload:
            text_parts = []
            html_parts = []
            # Prioritize text/plain
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain':
                     text_parts.append(self._extract_email_body(part))
                elif part.get('mimeType') == 'text/html':
                     html_parts.append(self._extract_email_body(part))
                elif part.get('mimeType', '').startswith('multipart/'):
                     # Recursively process nested multipart content
                     text_parts.append(self._extract_email_body(part)) # Add result directly

            # Prefer plain text if available
            if text_parts:
                return '\n\n---\n\n'.join(filter(None, text_parts))
            # Fallback to HTML if no plain text
            elif html_parts:
                 # Basic HTML tag stripping (consider a library like beautifulsoup4 for robust parsing)
                 import re
                 html_content = '\n\n---\n\n'.join(filter(None, html_parts))
                 text_content = re.sub('<[^>]+>', '', html_content) # Simple tag removal
                 return text_content
            else:
                return "(Multipart email with no text/plain or text/html parts found)"


        # If it's not multipart and has no body data (e.g., just an attachment placeholder)
        if not mime_type.startswith('multipart/'):
             return f"(No readable body content for mimeType: {mime_type})"

        return "(No text content found)" # Default placeholder
    
    def get_email_labels(self):
        """
        Retrieve available email labels from Gmail.
        
        Fetches the labels, formats them in a user-friendly way, and returns them.
        
        Returns:
            list: List of dictionaries with label id, name, and type.
        """        
        
        if not self.gmail_service:
            print(f"[{self.node_id}] Gmail service not available")
            return []
            
        try:
            results = self.gmail_service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            
            # Format labels for user-friendly display
            formatted_labels = []
            for label in labels:
                formatted_labels.append({
                    'id': label['id'],
                    'name': label['name'],
                    'type': label['type']  # 'system' or 'user'
                })
                
            return formatted_labels
            
        except Exception as e:
            print(f"[{self.node_id}] Error fetching email labels: {str(e)}")
            return []
            
    def process_advanced_email_command(self, command):
        """
        Process a complex email command using advanced parsing.
        
        First analyzes the command to extract detailed intent and parameters.
        Depending on the action (e.g., list_labels, advanced_search), it calls appropriate functions.
        
        Args:
            command (str): The advanced email command in natural language.
        
        Returns:
            str: The output or response from processing the advanced email command.
        """
        
        # First analyze the command to extract detailed intent and parameters
        analysis = self._analyze_email_command(command)
        
        action = analysis.get('action', 'none')
        
        if action == 'list_labels':
            # Get and format available labels
            labels = self.get_email_labels()
            if not labels:
                return "I couldn't retrieve your email labels."
                
            # Format response with label categories
            system_labels = [l for l in labels if l['type'] == 'system']
            user_labels = [l for l in labels if l['type'] == 'user']
            
            response = "Here are your email labels:\n\n"
            
            if system_labels:
                response += "System Labels:\n"
                for label in system_labels:
                    response += f"- {label['name']}\n"
            
            if user_labels:
                response += "\nCustom Labels:\n"
                for label in user_labels:
                    response += f"- {label['name']}\n"
                    
            return response
            
        elif action == 'advanced_search':
            # Extract search criteria from analysis
            criteria = analysis.get('criteria', {})
            
            if not criteria:
                return "I couldn't understand your search criteria. Please try again with more specific details."
                
            # Fetch emails matching criteria
            emails = self.fetch_emails_with_advanced_query(criteria)
            
            if not emails:
                return "I couldn't find any emails matching your criteria."
                
            # Summarize emails with requested format
            summary_type = analysis.get('summary_type', 'concise')
            return self.summarize_emails(emails, summary_type)
            
        else:
            # Fall back to basic email processing
            return self.process_email_command(command)
    
    def _analyze_email_command(self, command):
        """
        Analyze a complex email command to extract detailed parameters.
        
        This method sends a prompt to the LLM requesting a JSON output with the structure
        specifying action, criteria, and summary type.
        
        Args:
            command (str): The complex email command.
        
        Returns:
            dict: Parsed JSON with fields "action", "criteria", and "summary_type".
        """
        

        """Analyze a complex email command to extract detailed intent and parameters"""
        # If we're in email composition mode, skip this analysis
        if hasattr(self, 'email_context') and self.email_context.get('active'):
            return {"action": "none"}
            
        prompt = f"""
        Analyze this email-related command in detail:
        '{command}'
        
        Return a JSON object with the following structure:
        {{
            "action": "list_labels" | "advanced_search" | "fetch_recent" | "search" | "none",
            "criteria": {{
                "from": "sender email or name",
                "to": "recipient email",
                "subject": "subject text",
                "keywords": ["word1", "word2"],
                "has_attachment": true/false,
                "is_unread": true/false,
                "label": "label name",
                "after": "YYYY/MM/DD",
                "before": "YYYY/MM/DD",
                "max_results": 10
            }},
            "summary_type": "concise" | "detailed"
        }}
        
        Include only the fields that are explicitly mentioned or clearly implied in the command.
        Convert date references like "yesterday", "last week", "2 days ago" to YYYY/MM/DD format.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[{self.node_id}] Error analyzing email command: {str(e)}")
            return {"action": "none", "criteria": {}, "summary_type": "concise"}
        
    def _detect_send_email_intent(self, message):
        """Detect if the message is requesting to send an email"""
        # Skip this detection if we're already in email composition mode
        if hasattr(self, 'email_context') and self.email_context.get('active'):
            return {"is_send_email": False}
            
        prompt = f"""
        Analyze this message and determine if it's requesting to send an email:
        "{message}"
        
        A message is considered an email sending request if:
        1. It contains phrases like "send email", "write email", "send mail", "compose email", "draft email", etc.
        2. There's a clear intention to create and send an email to someone

        Return JSON with:
        - is_send_email: boolean (true if the message is about sending an email)
        - recipient: string (email address or name of recipient if specified, empty string if not)
        - subject: string (email subject line if specified, empty string if not)
        - body: string (email content if specified, empty string if not)
        - missing_info: array of strings (what information is missing: "recipient", "subject", "body")

        Notes:
        - If the message contains phrases like "subject:" or "title:" followed by text, extract that as the subject
        - If the message has text after keywords like "body:", "content:", or "message:", extract that as the body
        - If it says "the subject is" or "subject is" followed by text, extract that as the subject
        - If it says "the body is" or "message is" followed by text, extract that as the body
        - If no explicit markers are present but there's a clear distinction between subject and body, make your best guess
        - Look for paragraph breaks or sentence structure to identify where subject ends and body begins
        - For recipient, extract just the name or email (don't include words like "to" or "for")
        - If the message itself appears to be the content of the email, set body to the entire message excluding obvious command parts
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Determine what information is missing
            missing = []
            if not result.get('recipient'):
                missing.append('recipient')
            if not result.get('subject'):
                missing.append('subject')
            if not result.get('body'):
                missing.append('body')
                
            result['missing_info'] = missing
            
            return result
        except Exception as e:
            print(f"[{self.node_id}] Error detecting send email intent: {str(e)}")
            return {"is_send_email": False, "recipient": "", "subject": "", "body": "", "missing_info": []}

