from network.internal_communication import Intercom
from main import LLMNode  # Assuming LLMNode is in main.py and accessible
from secretary.utilities.logging import log_system_message, log_error
from config.agents import AGENT_CONFIG # Using the global AGENT_CONFIG for now

# Recommended: Define a separate default agent configuration for new users,
# or make AGENT_CONFIG more dynamic if it's intended to be user-specific.
DEFAULT_USER_AGENTS_CONFIG = AGENT_CONFIG # Or a subset/different config

class UserAgentManager:
    def __init__(self, user_id: str, db, socketio):
        """
        Manages agents, network, and interactions for a single user.

        Args:
            user_id (str): The unique identifier for the user.
            db: The database connection object.
            socketio: The SocketIO instance for real-time communication.
        """
        self.user_id = user_id
        self.db = db # Database for persistence (tasks, projects, etc.)
        self.socketio = socketio # For emitting events to user-specific rooms
        
        # Each user gets their own isolated network
        # User-specific log file for better traceability
        self.network = Intercom(log_file=f"communication_log_{self.user_id}.txt")
        
        self.agents = {}  # Stores LLMNode instances for this user: {node_id: LLMNode_instance}
        log_system_message(f"[UserAgentManager] Initialized for user: {self.user_id}")

    def initialize_default_agents(self):
        """
        Creates and registers a default set of agents for the user if they don't exist.
        These agents operate within the user's isolated network.
        """
        log_system_message(f"[UserAgentManager] Initializing default agents for user: {self.user_id}")
        
        # Here, you might want to fetch if user already has agents in DB to avoid re-creation
        # For now, we'll use a static config and create them if not in memory for this session.

        for agent_conf in DEFAULT_USER_AGENTS_CONFIG:
            # Ensure node_id is unique per user by prefixing with user_id
            original_agent_id = agent_conf['id']
            user_specific_node_id = f"{self.user_id}_{original_agent_id}"

            if user_specific_node_id in self.agents:
                log_system_message(f"Agent {user_specific_node_id} already exists in memory for user {self.user_id}.")
                continue

            # TODO: Check if this agent configuration should be fetched from DB for the user
            # or if it's okay to always create from a default config.

            try:
                node = LLMNode(
                    node_id=user_specific_node_id,
                    node_name=agent_conf['name'], # Use name from config
                    knowledge=agent_conf.get('knowledge', ''),
                    network=self.network,  # Crucial: use the user-specific network
                    user_id=self.user_id,  # Pass user_id to LLMNode
                    socketio_instance=self.socketio,  # Pass the UAM's socketio instance
                    # llm_api_key_override and llm_params can be sourced from agent_conf or user settings
                )
                self.network.register_node(node.node_id, node)
                self.agents[user_specific_node_id] = node
                log_system_message(f"[UserAgentManager] Created and registered LLMNode: {user_specific_node_id} for user: {self.user_id}")
                
                # Optional: Persist agent creation/details in the database, linked to user_id
                # self.db.save_or_update_agent_for_user(self.user_id, node.node_id, agent_conf)

            except Exception as e:
                log_error(f"[UserAgentManager] Failed to create agent {user_specific_node_id} for user {self.user_id}: {e}")
        
        log_system_message(f"[UserAgentManager] Default agents initialization complete for user: {self.user_id}. Total agents: {len(self.agents)}")

    def get_agents(self):
        """
        Returns a list of agent information for the current user.
        """
        agent_list = []
        for node_id, agent_instance in self.agents.items():
            agent_list.append({
                "id": agent_instance.node_id,
                "name": agent_instance.node_name, # Assuming LLMNode has node_name
                "user_id": agent_instance.user_id
                # Add other relevant agent details
            })
        return agent_list

    def send_message(self, target_node_id: str, message: str, sender_id: str):
        """
        Sends a message to a target agent within the user's network.
        Ensures the target_node_id is one of the user's agents.

        Args:
            target_node_id (str): The ID of the recipient agent (must be user-specific).
            message (str): The content of the message.
            sender_id (str): The ID of the sender (can be another agent or the user).

        Returns:
            A dictionary with the response or an error.
        """
        log_system_message(f"[UserAgentManager:{self.user_id}] Attempting to send message from '{sender_id}' to '{target_node_id}'")

        if target_node_id not in self.network.nodes: # Check against the user-specific network
            log_error(f"[UserAgentManager:{self.user_id}] Target node {target_node_id} not found in user's network.")
            return {"error": f"Node {target_node_id} not found for this user"}, 404

        # Ensure the node actually belongs to this manager's agents.
        # This is implicitly handled if self.network.nodes only contains this user's agents.
        target_agent = self.agents.get(target_node_id)
        if not target_agent : # or target_agent.user_id != self.user_id (double check)
             log_error(f"[UserAgentManager:{self.user_id}] Security: Target node {target_node_id} does not belong to user.")
             return {"error": "Access denied to node"}, 403
        
        try:
            # The LLMNode's receive_message should handle the core logic
            response_text = target_agent.receive_message(message, sender_id)
            log_system_message(f"[UserAgentManager:{self.user_id}] Message sent to {target_node_id}, response: {response_text}")
            return {
                "response": response_text,
                "terminal_output": "" # Placeholder if needed
            }
        except Exception as e:
            log_error(f"[UserAgentManager:{self.user_id}] Error processing message for node {target_node_id}: {e}")
            return {"error": str(e)}, 500

    # Add other methods as needed, e.g., for managing tasks, projects specifically for this user
    # if that logic is better suited here than directly in app.py calling db methods.
    # For example:
    # def get_user_tasks(self, agent_id_filter=None):
    #     return self.db.get_user_tasks(self.user_id, agent_id_filter)

    # def add_user_task(self, task_data):
    #     # task_data should not include user_id, as it's taken from self.user_id
    #     return self.db.create_task(self.user_id, task_data) 