import re, json
from datetime import datetime, timedelta
import openai

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

    def __init__(self, api_key: str, params: dict):
        """
        Args:
            api_key: Your OpenAI API key.
            params: Dict containing 'model', 'temperature', 'max_tokens', etc.
        """
        # Create a proper OpenAI client instance instead of using the module
        self.client = openai.OpenAI(api_key=api_key)
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
                "Provide short, to-the-point answers." #TODO: Improve
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
        socketio_instance=None,
        user_id: str = None
    ):
        self.node_id = node_id
        self.user_id = user_id  # Store user ID for data isolation

        # --- LLM client setup ---
        # Create a proper OpenAI client instance for this Brain
        self.client = openai.OpenAI(api_key=openai_api_key)
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
        self.projects = {}         # project plans by project_id (user-specific)

        self.meeting_context = {
            'active': False,
            'initial_message': None,
            'missing_info': [],
            'collected_info': {},
            'is_rescheduling': False
        }

        self.people = People()
        self.calendar = []
        self.context = []
        self.scheduler = None
        self.confirmation_context = {
            'active': False,
            'context': None,      # e.g. "schedule meeting", "cancel meeting"
            'initial_message': None,
            'start_datetime': None,
            'end_datetime': None,
            'project_id': None
        }
        self.calendar_service = None
        self.gmail_service    = None

        # --- SocketIO (if using realtime UI updates) ---
        self.socketio = socketio_instance

        log_system_message(f"[Brain:{self.node_id}] initialized for user: {user_id}.")
        
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
            raw = self.query_llm([{"role": "user", "content": prompt}])
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
            json_text = m.group(1) if m else raw.strip()
            data = json.loads(json_text)

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
        - participants: array of participants
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
        
    def initiate_project_planning(self, project_id: str, objective: str):
        """
        Initiates the project planning process (Version 2).

        This method sets up a new project or updates an existing one with the given
        objective. It then fetches candidate suggestions for project participation.
        The actual detailed planning and task generation are deferred until
        participants are confirmed by the user.

        The method updates the project's status to 'pending_final_participants'
        and sets up a confirmation context to manage the user interaction flow
        for participant selection.

        It leverages `_get_best_candidates_data` to obtain a list of suitable
        agents based on the project objective and available agent configurations.
        The suggested candidates are then formatted into a JSON string and returned
        as part of a message to the user.

        Args:
            project_id (str): The unique identifier for the project.
            objective (str): A description of the project's goals and scope.

        Returns:
            str: A message for the user, including an introduction and a JSON
                 payload of suggested candidate agents for the project.
        """
        log_system_message(f"[Brain] [{self.node_id}] Initiating project '{project_id}' with objective: {objective}")

        if project_id not in self.projects:
            # Initialize a new project if it doesn't exist
            self.projects[project_id] = {
                "name": "Project " + project_id,
                "objective": objective,
                #"description": objective, # Description can be objective initially
                "plan_steps": [],  # Plan steps will be populated later
                "participants": set(),  # Participants will be added by the user
                "status": "pending_final_participants",  # Initial status
                "created_at": datetime.now().isoformat()
            }
            # Activate confirmation context for participant selection
            self.confirmation_context['active'] = True
            self.confirmation_context['context'] = "plan project"
            self.confirmation_context['initial_message'] = f"Initiating project planning for '{project_id}' with objective: {objective}"
            self.confirmation_context['project_id'] = project_id
        else: 
            # Update an existing project
            self.projects[project_id]["objective"] = objective
            self.projects[project_id]["description"] = objective # Update description as well
            self.projects[project_id]["status"] = "pending_final_participants" # Reset status for new planning phase
            self.projects[project_id]["participants"] = set() # Reset participants for new planning

        # Get candidate suggestions using the internal helper method
        suggested_candidates_data = self._get_best_candidates_data(project_id, objective)

        # Format the response string to be compatible with the UI's current parsing logic
        response_intro = f"Here are the best-suited candidates for your project '{project_id}':"
        response_json_payload = json.dumps(suggested_candidates_data)
        
        return f"{response_intro}\\n{response_json_payload}"

    #TODO: Remove this method once the LLM is able to generate the candidates data
    def _get_default_candidates_data(self) -> list[dict]:
        """
        Provides a default list of candidate data.

        This method serves as a fallback when candidate suggestions cannot be
        generated dynamically (e.g., due to LLM errors or empty configurations).
        It returns a predefined list of sample agent profiles.

        Returns:
            list[dict]: A list of dictionaries, where each dictionary represents
                        a default candidate agent with their details (name,
                        department, skills, title, description).
        """
        return [
            {"name": "Ueli Maurer", "department": "Engineering", "skills": ["Swiss German", "AI", "System Design"], "title": "CEO", "description": "Oversees the entire organization and strategy."},
            {"name": "John Doe", "department": "Marketing", "skills": ["English", "Marketing", "Market Analysis"], "title": "Marketing Lead", "description": "Handles marketing campaigns and market analysis."},
            {"name": "Michael Chen", "department": "Engineering", "skills": ["Chinese", "Agile", "Market Analysis"], "title": "Engineering Lead", "description": "Manages the technical team and codebase."}
        ]

    def _create_candidates_data_from_ids(self, agent_ids: list[str]) -> list[dict]:
        """
        Constructs a list of candidate data dictionaries from a list of agent IDs.

        This method iterates through the provided `agent_ids`, looks up each ID
        in the `AGENT_CONFIG` (case-insensitively), and compiles a list of
        dictionaries containing detailed information for each found agent.
        If no candidates are found for the given IDs or if `agent_ids` is empty,
        it falls back to returning default candidate data.

        Args:
            agent_ids (list[str]): A list of agent identifiers to look up.

        Returns:
            list[dict]: A list of dictionaries, where each dictionary contains
                        the 'name', 'department', 'skills', 'title', and
                        'description' for a matched agent. Returns default
                        candidate data if no matches are found or input is empty.
        """
        candidates_data = []
        for agent_id_lookup in agent_ids:
            # Find the agent configuration entry matching the agent ID (case-insensitive)
            agent_config_entry = next((a for a in AGENT_CONFIG if a["id"].lower() == agent_id_lookup.lower()), None)
            if agent_config_entry:
                candidates_data.append({
                    "name": agent_config_entry["name"],
                    "department": agent_config_entry["department"],
                    "skills": agent_config_entry["skills"],
                    "title": agent_config_entry["title"],
                    "description": agent_config_entry["description"]
                })
        
        # If no candidates were found from the provided IDs, return default data
        if not candidates_data:
            return self._get_default_candidates_data()
        return candidates_data
    
    def _process_agent_ids(self, agent_ids: list[str]) -> list[str]:
        """
        Processes a list of potentially varied agent identifiers and maps them
        to standardized agent IDs from `AGENT_CONFIG`.

        This method handles several formats for agent identification:
        1.  Direct match with an agent's 'id' in `AGENT_CONFIG`.
        2.  "agent_N" or "agentN" format, where N is a 1-based index into `AGENT_CONFIG`.
        3.  Numeric string "N", interpreted as a 1-based index into `AGENT_CONFIG`.
        4.  Direct match with an agent's 'name' (case-insensitive) in `AGENT_CONFIG`.

        The method ensures that the returned list contains unique, valid agent IDs.

        Args:
            agent_ids (list[str]): A list of agent identifiers which may be in
                                   various formats (e.g., "Ueli Maurer", "agent_1", "1").

        Returns:
            list[str]: A list of unique, standardized agent IDs derived from the
                       input. If an ID cannot be resolved, it's omitted.
        """
        processed_ids = []
        for agent_id in agent_ids:
            # Check for direct ID match
            if any(a["id"] == agent_id for a in AGENT_CONFIG):
                processed_ids.append(agent_id)
                continue
            
            # Handle "agent_N" or "agentN" format
            if agent_id.lower().startswith("agent"):
                num_part = agent_id.lower().replace("agent", "").replace("_", "").strip()
                try:
                    idx = int(num_part) - 1  # Convert to 0-based index
                    if 0 <= idx < len(AGENT_CONFIG):
                        processed_ids.append(AGENT_CONFIG[idx]["id"])
                        continue
                except ValueError:
                    # num_part was not a valid integer
                    pass
            
            # Handle numeric string "N" as 1-based index
            try:
                idx = int(agent_id) - 1  # Convert to 0-based index
                if 0 <= idx < len(AGENT_CONFIG):
                    processed_ids.append(AGENT_CONFIG[idx]["id"])
                    continue
            except ValueError:
                # agent_id was not a simple integer string
                pass

            # Handle matching by agent name (case-insensitive)
            agent_id_lower = agent_id.lower()
            for agent in AGENT_CONFIG:
                if agent["name"].lower() == agent_id_lower or agent["id"].lower() == agent_id_lower:
                    processed_ids.append(agent["id"])
                    break
        return list(set(processed_ids)) # Ensure uniqueness in the final list

    def _extract_agent_ids_from_text(self, text: str) -> list[str]:
        """
        Attempts to extract agent IDs from a given text string, typically when
        direct JSON parsing of an LLM response fails.

        This method employs several strategies:
        1.  Regex patterns to find "agent_N", "agent N", or standalone numbers (interpreted as 1-based indices).
        2.  If regex fails, it searches for direct mentions of agent IDs or names (case-insensitive) from `AGENT_CONFIG`.
        3.  As a last resort, if no IDs are found and `AGENT_CONFIG` is populated,
            it defaults to returning the IDs of the first three agents in the configuration.

        The method returns up to three unique agent IDs.

        Args:
            text (str): The text string from which to extract agent IDs.

        Returns:
            list[str]: A list of extracted and potentially resolved agent IDs,
                       containing up to three unique IDs.
        """
        found_ids = []
        # Regex patterns to find "agent_X" or "X" (numeric index)
        agent_patterns = [
            r'agent[_\s]*(\\d+)', # Matches "agent_1", "agent 1", etc.
            r'\\b(\\d+)\\b'      # Matches standalone numbers, e.g., "1", "2"
        ]
        for pattern in agent_patterns:
            matches = re.findall(pattern, text.lower())
            for match in matches:
                try:
                    # Attempt to map number to 0-based index in AGENT_CONFIG
                    idx = int(match) -1 
                    if 0 <= idx < len(AGENT_CONFIG):
                        found_ids.append(AGENT_CONFIG[idx]["id"])
                        continue
                except ValueError:
                    pass
                # Fallback to agent_N format if direct index mapping fails or isn't applicable
                found_ids.append(f"agent_{match}") 

        # If regex patterns yield no results, try matching known agent IDs or names
        if not found_ids:
            for agent in AGENT_CONFIG:
                if agent["id"].lower() in text.lower() or agent["name"].lower() in text.lower():
                    found_ids.append(agent["id"])
        
        # As a final fallback, if no IDs are found and AGENT_CONFIG exists, use the first few agents
        if not found_ids and AGENT_CONFIG:
            # Return IDs of the first up to 3 agents
            found_ids = [agent["id"] for agent in AGENT_CONFIG[:3]]
        
        # Return unique IDs, limited to a maximum of 3
        return list(set(found_ids))[:3] #TODO: Remove this limit once the LLM is able to generate the optimal number of candidates

    def _get_best_candidates_data(self, project_id: str, objective: str) -> list[dict]:
        """
        Utilizes an LLM to suggest the most suitable candidate agents for a project
        based on its objective.

        This method constructs a detailed prompt for the LLM, including:
        - The project ID and objective.
        - A comprehensive list of available agents, with their ID, name, department,
          title, skills, description, and knowledge areas, sourced from `AGENT_CONFIG`.
        - Instructions for the LLM to analyze the project requirements and select
          up to three best-suited candidates.
        - A strict requirement for the LLM to respond ONLY with a valid JSON object
          containing an array of exact agent IDs (e.g., `{"selected_agents": ["id_1", "id_2"]}`).

        The method handles LLM response parsing, including cleaning potential markdown
        code blocks. If JSON parsing fails, it attempts to extract agent IDs using
        `_extract_agent_ids_from_text`. The processed agent IDs are then converted
        into candidate data dictionaries using `_create_candidates_data_from_ids`.

        If the LLM response is empty, parsing fails repeatedly, or any other
        exception occurs, it falls back to `_get_default_candidates_data`.

        Args:
            project_id (str): The identifier of the project.
            objective (str): The detailed objective or description of the project.

        Returns:
            list[dict]: A list of dictionaries, where each dictionary represents a
                        suggested candidate agent with their details. Returns default
                        candidates in case of errors or empty LLM response.
        """
        agent_info_list = []
        # Prepare detailed information for each agent to include in the prompt
        for i, agent in enumerate(AGENT_CONFIG):
            agent_info = (
                f"Agent ID: {agent['id']}\\n"
                f"Name: {agent['name']}\\n"
                f"Department: {agent['department']}\\n"
                f"Title: {agent['title']}\\n"
                f"Skills: {', '.join(agent['skills'])}\\n"
                f"Description: {agent['description']}\\n"
                f"Knowledge: {agent['knowledge']}\\n"
            )
            agent_info_list.append(agent_info)
        agents_info = "\\n\\n".join(agent_info_list)

        # Construct the prompt for the LLM
        prompt_content = f"""Given the following project objective (which may include itemized lists and other structures) and available agents, select up to 3 best-suited candidates for the project.
            Thoroughly analyze all details provided in the multi-line 'Project Objective' to understand the full scope and requirements.
            Consider their skills, experience, and knowledge when making the selection.

            Project ID: {project_id}
            Project Objective:{objective}

            Available Agents:
            {agents_info}

            Please analyze the project requirements and select the most suitable candidates. Consider:
            1. Required skills and expertise
            2. Department relevance
            3. Role and responsibilities
            4. Knowledge areas

            IMPORTANT: You must ONLY respond with a valid JSON object containing an array of the EXACT agent IDs as listed above.
            The response MUST follow this exact format: {{"selected_agents": ["exact_id_1", "exact_id_2", "exact_id_3"]}}
            For example, if you select Ueli Maurer, use the exact ID "Ueli Maurer".
            Use the exact agent ID strings from the Agent ID field for each agent.
            Do not include any explanation or other text outside the JSON object.
        """
        
        messages = [
            {"role": "system", "content": "You are a project management expert who helps select the best team members for projects. You always respond with valid JSON using exact agent IDs from the provided list."},
            {"role": "user", "content": prompt_content}
        ]

        try:
            log_api_request("openai_chat_candidates", {"model": self.llm_params["model"], "messages": messages})
            # Query the LLM for candidate suggestions
            resp = self.client.chat.completions.create(
                model=self.llm_params.get("model", "gpt-4o-mini"), # Use model from llm_params or default
                messages=messages,
                temperature=self.llm_params.get("temperature", 0.3), # Use temperature from llm_params or default
                max_tokens=self.llm_params.get("max_tokens", 150)    # Use max_tokens from llm_params or default
            )
            result_content = resp.choices[0].message.content.strip()
            log_api_response("openai_chat_candidates", {"response": result_content})

            # Handle empty or whitespace-only response
            if not result_content or result_content.isspace():
                log_warning(f"[{self.node_id}] Empty response from OpenAI for candidate suggestion.")
                return self._get_default_candidates_data()

            # Clean the response content (e.g., remove markdown ```json ... ```)
            clean_content = result_content.strip()
            if clean_content.startswith("```") and clean_content.endswith("```"):
                clean_content = clean_content.strip("```")
                if clean_content.startswith("json"): # Remove "json" prefix if present
                    clean_content = clean_content[4:].strip()
            
            selected_agent_ids = []
            try:
                # Attempt to find and parse JSON if it's embedded in other text
                if not clean_content.startswith('{'): 
                    json_start = clean_content.find('{')
                    json_end = clean_content.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        clean_content = clean_content[json_start:json_end]
                
                result = json.loads(clean_content)
                # Get the list of selected agent IDs, limit to 3
                selected_agent_ids = result.get("selected_agents", [])[:3] #TODO: Remove this limit once the LLM is able to generate the optimal number of candidates
            except json.JSONDecodeError:
                # If JSON parsing fails, try manual extraction from text
                log_warning(f"[{self.node_id}] JSON parsing error for candidates: {clean_content}. Trying manual extraction.")
                selected_agent_ids = self._extract_agent_ids_from_text(clean_content)
            
            # Process the extracted/parsed agent IDs to resolve them to standard forms
            processed_agent_ids = self._process_agent_ids(selected_agent_ids)
            # Create structured candidate data from the processed IDs
            candidates_data = self._create_candidates_data_from_ids(processed_agent_ids)
            
            if candidates_data:
                return candidates_data
            # Fallback to default if no valid candidate data could be created
            return self._get_default_candidates_data()

        except Exception as e:
            log_error(f"[{self.node_id}] Error getting best candidates: {str(e)}")
            # Fallback to default candidates in case of any exception during the process
            return self._get_default_candidates_data()


    def add_participant_to_project(self, project_id: str, participant_name: str) -> str:
        """
        Adds a specified participant to a project.

        This method locates the project by `project_id`. If found, it adds the
        `participant_name` to the project's set of participants.
        The `participants` attribute of the project is ensured to be a set to
        maintain uniqueness.

        If a `socketio` instance is available, it emits an 'update_projects' event
        to notify connected clients of the change.

        Args:
            project_id (str): The unique identifier of the project.
            participant_name (str): The name or identifier of the participant to add.

        Returns:
            str: A confirmation message indicating the outcome, including the
                 updated list of participants if successful, or an error message
                 if the project is not found.
        """
        log_system_message(f"[Brain] [{self.node_id}] Adding participant '{participant_name}' to project '{project_id}'")
        if project_id not in self.projects:
            log_warning(f"[Brain] [{self.node_id}] Project '{project_id}' not found for adding participant.")
            return f"Project '{project_id}' not found."

        # Ensure the 'participants' field is a set for the project
        if not isinstance(self.projects[project_id].get("participants"), set):
            self.projects[project_id]["participants"] = set()

        self.projects[project_id]["participants"].add(participant_name)
        log_system_message(f"[Brain] [{self.node_id}] Current participants for '{project_id}': {self.projects[project_id]['participants']}")
        
        # Emit an update to the UI via SocketIO if available
        if self.socketio:
            self.socketio.emit('update_projects', room=self.node_id) # Or a general room if needed
        
        return f"Added '{participant_name}' to project '{project_id}'. Current participants: {', '.join(self.projects[project_id]['participants'])}."

    def finalize_and_plan_project(self, project_id: str) -> str:
        """
        Finalizes the participant list for a project and proceeds to detailed
        planning and task generation.

        This method is typically called after the user has confirmed the selection
        of participants for the project identified by `project_id`.

        It performs the following steps:
        1.  Validates that the project exists and is in the 'pending_final_participants' status.
        2.  Retrieves the project's objective and the finalized list of participants.
        3.  Checks if any participants have been added; if not, it updates the project
            status to 'failed_no_participants' and returns an error message.
        4.  Calls `plan_project` to generate a detailed project plan and associated tasks.
        5.  Updates the project's status based on the outcome of `plan_project`
            (e.g., 'planned_and_tasks_generated', 'planning_failed').
        6.  If `socketio` is available, emits 'update_projects' and 'update_tasks'
            events to notify clients.

        Args:
            project_id (str): The unique identifier of the project to finalize and plan.

        Returns:
            str: A message summarizing the outcome of the planning process. This
                 message includes the result from `plan_project`.
        """
        log_system_message(f"[Brain] [{self.node_id}] Finalizing planning for project '{project_id}'")
        
        # Check if the project exists
        if project_id not in self.projects:
            log_warning(f"[Brain] [{self.node_id}] Project '{project_id}' not found for finalization.")
            return f"Project '{project_id}' not found."

        project_data = self.projects[project_id]
        # Check if the project is in the correct state for finalization
        if project_data["status"] != "pending_final_participants":
            log_warning(f"[Brain] [{self.node_id}] Project '{project_id}' is not in 'pending_final_participants' state. Current state: {project_data['status']}")
            return f"Project '{project_id}' is not awaiting finalization. Current status: {project_data['status']}."

        objective = project_data["objective"]
        final_participants = list(project_data["participants"]) # Convert set to list for plan_project

        # Ensure there are participants before proceeding
        if not final_participants:
            log_warning(f"[Brain] [{self.node_id}] No participants added to project '{project_id}'. Cannot proceed with planning.")
            project_data["status"] = "failed_no_participants"
            return f"No participants were added to project '{project_id}'. Planning cannot proceed. Please add participants and try finalizing again."

        log_system_message(f"[Brain] [{self.node_id}] Proceeding to detailed plan generation for '{project_id}' with participants: {final_participants}")
        
        # Call the plan_project method to generate the plan and tasks
        plan_result = self.plan_project(project_id, objective, final_participants)
        
        # Update project status based on the outcome of the planning process
        # plan_project internally calls generate_tasks_from_plan.
        # The status update reflects that planning and task generation have been attempted.
        if "successfully planned" in plan_result.lower(): # Check for success message from plan_project
            project_data["status"] = "planned_and_tasks_generated"
        else:
            project_data["status"] = "planning_failed" 

        # Emit updates to the UI via SocketIO if available
        if self.socketio:
            self.socketio.emit('update_projects', room=self.node_id)
            self.socketio.emit('update_tasks', room=self.node_id)

        return plan_result

    def plan_project(self, project_id: str, objective: str, final_participants: list):
        """
        Creates a detailed project plan using an LLM and generates associated tasks.

        This method orchestrates the generation of a structured project plan based on
        the project's objective and a finalized list of participants. It involves:
        1.  Initializing or updating the project entry in `self.projects` with the
            provided objective and participants, and setting its status to "planning".
        2.  Constructing a detailed prompt for an LLM to break down the project
            objective into 3-5 high-level steps. For each step, the LLM is asked
            to provide a name, description, and assign responsible participants from
            the `final_participants` list.
        3.  Querying the LLM and parsing its response, which is expected to be a JSON
            object containing "plan_steps".
        4.  Storing the generated plan steps in the project data and updating the
            project status to "plan_generated".
        5.  If plan steps are successfully generated, it calls `generate_tasks_from_plan`
            to create specific tasks for these steps.
        6.  Updating the project status further based on the outcome of task generation
            (e.g., "tasks_generated", "task_generation_failed").
        7.  Emitting 'update_projects' and 'update_tasks' events via SocketIO if
            available, to inform the UI of changes.

        Error handling is included for LLM communication issues, JSON parsing errors,
        and other exceptions during the planning process.

        Args:
            project_id (str): The unique identifier for the project.
            objective (str): The detailed objective or description of the project.
            final_participants (list): A list of names or identifiers of the
                                       participants finalized for this project.

        Returns:
            str: A message summarizing the outcome of the planning and task generation
                 process. This includes details of the generated plan or error messages
                 if the process failed.
        """
        log_system_message(f"[Brain] [{self.node_id}] Generating detailed plan for '{project_id}' with objective: {objective} and participants: {final_participants}")

        # Ensure project exists or initialize it for planning
        if project_id not in self.projects:
            # This case should ideally be handled before calling this, but as a safeguard:
            self.projects[project_id] = {
                "name": "Project " + project_id,
                "objective": objective,
                "description": objective, # Initialize description with objective
                "plan_steps": [],
                "participants": set(final_participants), # Store participants as a set
                "status": "planning", # Set intermediate status
                "created_at": datetime.now().isoformat()
            }
        else:
            # Update existing project details for replanning or continuation
            self.projects[project_id]["objective"] = objective
            self.projects[project_id]["participants"] = set(final_participants) # Ensure it's a set and updated
            self.projects[project_id]["status"] = "planning"
        
        # Construct the prompt for the LLM to generate a project plan
        plan_prompt = f"""
        You are creating a detailed project plan for project '{project_id}'.
        Project Objective (This may be a multi-line description with itemized lists. Consider all details carefully):
        {objective}
        Project Participants: {', '.join(final_participants)}. These are the only individuals/roles involved.

        Break down the objective into a sequence of 3-5 high-level steps.
        For each step, provide:
        - A short "name" for the step.
        - A concise "description" of what the step entails.
        - Assign "responsible_participants" from the provided Project Participants list. This should be a list of one or more participants.

        Respond ONLY with a valid JSON object containing a single key "plan_steps",
        which is an array of these step objects.
        Example:
        {{
          "plan_steps": [
            {{
              "name": "Initial Research",
              "description": "Conduct market research and gather initial requirements.",
              "responsible_participants": ["marketing", "ceo"]
            }},
            {{
              "name": "Development Phase 1",
              "description": "Develop core features based on research.",
              "responsible_participants": ["engineering"]
            }}
          ]
        }}
        Ensure all "responsible_participants" are strictly from the list: {', '.join(final_participants)}.
        """

        try:
            # Query the LLM to get the project plan
            raw_response = self.query_llm([{"role": "user", "content": plan_prompt}])
            
            # Clean the LLM response to extract JSON
            json_text = raw_response.strip()
            if json_text.startswith("```json"): # Remove markdown code block notation
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            json_text = json_text.strip()

            # Parse the JSON response
            plan_data = json.loads(json_text)
            plan_steps = plan_data.get("plan_steps", [])


            self.projects[project_id]["plan_steps"] = plan_steps
            self.projects[project_id]["status"] = "plan_generated" # Update status after plan generation
            log_system_message(f"[Brain] [{self.node_id}] Project plan generated for '{project_id}': {plan_steps}")

            # Check if the LLM returned any plan steps
            if not plan_steps:
                log_error(f"[Brain] [{self.node_id}] LLM did not return valid plan steps for project '{project_id}'. Response: {raw_response}")
                self.projects[project_id]["status"] = "planning_failed_no_steps"
                return f"Failed to generate a project plan for '{project_id}'. The LLM did not provide actionable steps."

            # Generate tasks based on the created plan
            task_generation_result = self.generate_tasks_from_plan(project_id, plan_steps, final_participants)
            
            # Update project status based on the outcome of task generation
            if "task generation process completed" in task_generation_result.lower(): # Check for success message from generate_tasks_from_plan
                 self.projects[project_id]["status"] = "tasks_generated"
                 final_message = f"Project '{project_id}' successfully planned and tasks generated for participants: {', '.join(final_participants)}. {task_generation_result}"
            else:
                 self.projects[project_id]["status"] = "task_generation_failed"
                 final_message = f"Project '{project_id}' planned, but task generation failed. {task_generation_result}"
            
            # Emit updates to UI via SocketIO if available
            if self.socketio:
                self.socketio.emit('update_projects', room=self.node_id) # Update project details (status, plan)
                self.socketio.emit('update_tasks', room=self.node_id)    # Update tasks list

            return final_message

        except json.JSONDecodeError as e:
            log_error(f"[Brain] [{self.node_id}] Failed to parse LLM response for project plan '{project_id}'. Error: {e}. Response: {raw_response}")
            self.projects[project_id]["status"] = "planning_failed_parse_error"
            return f"Failed to parse project plan for '{project_id}'. Invalid format from LLM."
        except Exception as e:
            log_error(f"[Brain] [{self.node_id}] Error during project planning for '{project_id}': {str(e)}")
            self.projects[project_id]["status"] = "planning_failed_exception"
            return f"An unexpected error occurred while planning project '{project_id}': {str(e)}"

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
            
            # Ensure responsible_participants are from the main project participants list for this step
            step_responsible_participants = step.get("responsible_participants", [])
            # Filter to ensure only valid project participants are considered for this step's tasks
            valid_task_assignees_for_step = [p for p in step_responsible_participants if p in participants]
            if not valid_task_assignees_for_step:
                # If a step in the plan has no valid assignees from the project's final list,
                # fall back to the general project participants for task assignment for this step.
                # This can happen if the LLM hallucinated participants during plan generation.
                log_warning(f"[Brain] [{self.node_id}] Step '{step.get('name')}' had no valid assignees from project participants. Using project participants: {participants} for task assignment.")
                valid_task_assignees_for_step = participants
            
            if not valid_task_assignees_for_step: # Still no one? Skip task gen for this step.
                log_warning(f"[Brain] [{self.node_id}] No valid assignees for step '{step.get('name')}' in project '{project_id}'. Skipping task generation for this step.")
                continue


            # Refined prompt to be very clear about using the provided participants
            current_participants_list_str = ", ".join(valid_task_assignees_for_step) # Use filtered list for this step
            prompt = f"""
            For project '{project_id}', analyze this step: "{step_description}" (Step Name: "{step.get("name", "N/A")}")
            
            Based on this step, create a suitable number of specific, actionable tasks (generally 1-3 tasks, but up to a maximum of 5 tasks for this step if necessary to ensure all participants are assigned a task).
            
            The ONLY available assignees for these tasks are from this list: {current_participants_list_str}.
            Each task MUST be assigned to one or more of these participants. Do not assign tasks to roles/names not in this list.
            Ensure the 'assigned_to' field in your function call strictly uses names from this list.
            For example, if '{current_participants_list_str}' contains 'engineering' and 'marketing', 'assigned_to' can be 'engineering', or 'marketing', or 'engineering, marketing'.

            CRITICAL REQUIREMENT: Every participant in the list ({current_participants_list_str}) MUST be assigned to at least one of the tasks you create for this step. Distribute task responsibilities logically among them. If a participant cannot be logically assigned a task from the primary step description, you can create a related sub-task or a review task for them, ensuring it's relevant to the step and the project.
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
                                    project_id=project_id,
                                    user_id=self.user_id
                                )
                                
                                # Add to network tasks
                                if self.network:
                                    self.network.add_task(task)
                                    print(f"[{self.node_id}] Created task: {task}")
                                    
                                    # Create a calendar reminder for the task
                                    # This should probably return a collective result after all steps.
                                    # For now, let's assume scheduler.create_calendar_reminder is robust.
                                    if hasattr(self, 'scheduler') and self.scheduler:
                                         self.scheduler.create_calendar_reminder(task) # Fire-and-forget for now
                                else:
                                    log_warning(f"[{self.node_id}] Network not available, task '{task.title}' not added to network tasks.")
            
            except Exception as e:
                print(f"[{self.node_id}] Error generating tasks for step {i+1}: {e}")
                log_error(f"[Brain] [{self.node_id}] Error generating tasks for project '{project_id}', step '{step.get('name')}': {e}")
                # Continue to next step, don't let one step's failure stop all task generation.

        # After processing all steps, emit a task update through socketio if available
        if self.socketio:
            self.socketio.emit('update_tasks', room=self.node_id) # Or a general room
            log_system_message(f"[Brain] [{self.node_id}] Emitted update_tasks for project '{project_id}'")
            
        # Format the project plan for the output, assuming HTML rendering
        project_plan_details = self.projects[project_id].get("plan_steps", [])
        formatted_plan = f"<br><br><b>Project Plan for '{project_id}':</b><br>"
        if project_plan_details:
            for step in project_plan_details:
                participants_str = ", ".join(step.get("responsible_participants", ["N/A"]))
                # Using HTML for formatting
                formatted_plan += (
                    f"<br>- <b>Step:</b> {step.get('name', 'N/A')}<br>"
                    f"&nbsp;&nbsp;- <b>Description:</b> {step.get('description', 'N/A')}<br>"
                    f"&nbsp;&nbsp;- <b>Responsible:</b> {participants_str}<br>"
                )
        else:
            formatted_plan += "<br>No plan steps found.<br>"

        return f"Task generation process completed for project '{project_id}'. Check task list for details.{formatted_plan}"

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
                    charset = 'utf-8' # Default
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

        if 'parts' in payload:
            text_parts = []
            html_parts = []
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


