import openai
import json
from typing import Dict, Optional

# Set your OpenAI API key (or via environment variable)
openai.api_key = "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"

class Network:
    def __init__(self, log_file: Optional[str] = None):
        self.nodes: Dict[str, LLMNode] = {}
        self.log_file = log_file

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


class LLMNode:
    def __init__(self, node_id: str, knowledge: str = "",
                 llm_api_key: str = "", llm_params: dict = None):
        """
        Changes:
          - Lowered temperature to reduce verbosity and randomness.
          - We'll add a 'calendar' structure to track scheduled meetings.
        """
        self.node_id = node_id
        self.knowledge = knowledge

        # If each node can have its own API key, set it here. Otherwise, rely on global openai.api_key.
        self.llm_api_key = llm_api_key
        if self.llm_api_key:
            openai.api_key = self.llm_api_key

        # Make responses short and direct
        self.llm_params = llm_params if llm_params else {
            "model": "gpt-3.5-turbo",
            "temperature": 0.0,    # Very low => more concise, deterministic
            "max_tokens": 10000000     # Limit the length of responses
        }

        # Store conversation if needed (but we'll be minimal now)
        self.conversation_history = []

        # For multiple projects, store them in a dict:
        # { project_id: { "name": ..., "plan": [...], "participants": set(...) } }
        self.projects = {}

        # Each node has a calendar for scheduling
        self.calendar = []  # list of tuples/dicts, e.g., {"project_id":..., "time":...}

        self.network: Optional[Network] = None

    def receive_message(self, message: str, sender_id: str):
        """
        Receive a message from another node or user.
        Changes:
         - We no longer auto-respond with multiple turns. Instead, we do a single short reply if needed.
         - We keep conversation short: instruct the LLM to be direct and then end.
        """
        print(f"[{self.node_id}] Received from {sender_id}: {message}")

        # Append to short-term memory
        self.conversation_history.append({"role": "user", "content": f"{sender_id} says: {message}"})

        # We'll decide if we want to generate exactly ONE response or skip.
        # For demonstration, let's always generate exactly one short response if it's not "plan_project".
        # If you want no auto-reply, comment out the block below.
        if "plan" not in message and "meeting" not in message:
            response = self.query_llm(self.conversation_history)
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": response})
            # Send a single message back
            self.send_message(sender_id, response)
        # If there's any custom logic to detect that info is fully shared, you can skip sending a reply.

    def send_message(self, recipient_id: str, content: str):
        if not self.network:
            print(f"[{self.node_id}] No network attached.")
            return
        self.network.send_message(self.node_id, recipient_id, content)

    def query_llm(self, messages):
        """
        We'll use a system prompt that instructs the LLM to be short, direct, and end the conversation.
        """
        system_prompt = [{
            "role": "system",
            "content": (
                "You are a direct and concise AI agent for an organization. "
                "Provide short, to-the-point answers. Do not continue the conversation further than necessary. "
                "End after conveying necessary information."
            )
        }]

        # Combine system prompt + messages
        combined_messages = system_prompt + messages

        try:
            completion = openai.Chat.create(
                model=self.llm_params["model"],
                messages=combined_messages,
                temperature=self.llm_params.get("temperature", 0.0),
                max_tokens=self.llm_params.get("max_tokens", 100)
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[{self.node_id}] LLM query failed: {e}")
            return "LLM query failed."

    def plan_project(self, project_id: str, objective: str):
        """
        Create a project plan. Then schedule a meeting for the roles involved.
        Changes:
         - The plan is short and direct.
         - Once the plan is parsed, we automatically schedule a meeting with all participants.
        """
        if project_id not in self.projects:
            self.projects[project_id] = {
                "name": objective,
                "plan": [],
                "participants": set()
            }

        plan_prompt = f"""
        You are creating a short project plan for project '{project_id}'.
        Objective: {objective}

        Return valid JSON only, with this structure:
        {{
          "plan": [
            {{
              "role": "string, e.g. 'marketing', 'engineering'",
              "action": "short next step"
            }}
          ]
        }}
        Keep it concise. End after providing the JSON. No extra words.
        """

        response = self.query_llm([{"role": "user", "content": plan_prompt}])
        print(f"[{self.node_id}] LLM raw response (project '{project_id}'): {response}")

        # Try to parse JSON
        try:
            data = json.loads(response)
            plan_list = data.get("plan", [])
            self.projects[project_id]["plan"] = plan_list

            # We'll message relevant roles
            role_to_node = {
                "marketing": "marketing",
                "engineering": "engineering",
                "design": "design",
                "ceo": "ceo"
            }

            participants = []
            for item in plan_list:
                role = item.get("role", "").lower()
                action = item.get("action", "")
                if role in role_to_node:
                    participants.append(role_to_node[role])
                    self.send_message(role_to_node[role],
                                      f"Project '{project_id}': {action}\nObjective: {objective}")
                    self.projects[project_id]["participants"].add(role_to_node[role])
                else:
                    print(f"[{self.node_id}] No mapping for role '{role}'. Skipping.")

            # Once the plan is set, schedule a meeting for participants
            self.schedule_meeting(project_id, participants)

        except json.JSONDecodeError as e:
            print(f"[{self.node_id}] Failed to parse JSON plan: {e}")

    def schedule_meeting(self, project_id: str, participants: list):
        """
        Simulate setting up a meeting. We'll assume a simple text 'Meeting for project X'.
        Then each participant can add it to their own calendars.
        """
        meeting_description = f"Meeting for project '{project_id}'"
        # Just store a placeholder in this node's calendar
        self.calendar.append({
            "project_id": project_id,
            "meeting_info": meeting_description
        })
        print(f"[{self.node_id}] Scheduled meeting for '{project_id}' with: {participants}")

        # Notify participants so they add it to their calendars
        for p in participants:
            if p in self.network.nodes:
                self.network.nodes[p].calendar.append({
                    "project_id": project_id,
                    "meeting_info": meeting_description
                })
                print(f"[{self.node_id}] Notified {p} to add meeting for project '{project_id}'.")


def run_cli(network):
    print("Commands:\n"
          "  node_id: message => send 'message' to 'node_id'\n"
          "  node_id: plan project_id = objective => create a new project plan\n"
          "  quit => exit\n")

    while True:
        user_input = input("> ")
        if user_input.lower() == "quit":
            break

        # Plan project command
        if "plan" in user_input and "=" in user_input:
            try:
                # e.g. "ceo: plan p123 = Build AI feature"
                node_part, plan_part = user_input.split("plan", 1)
                node_id = node_part.replace(":", "").strip()
                plan_part = plan_part.strip()
                project_id_part, objective_part = plan_part.split("=", 1)
                project_id = project_id_part.strip()
                objective = objective_part.strip()

                if node_id in network.nodes:
                    network.nodes[node_id].plan_project(project_id, objective)
                else:
                    print(f"No node found: {node_id}")
            except Exception as e:
                print(f"Error parsing plan command: {e}")
        else:
            # normal message command: "node_id: some message"
            if ":" not in user_input:
                print("Invalid format. Use 'node_id: message' or 'node_id: plan project_id = objective'.")
                continue
            node_id, message = user_input.split(":", 1)
            node_id = node_id.strip()
            message = message.strip()

            if node_id in network.nodes:
                network.nodes[node_id].receive_message(message, "cli_user")
            else:
                print(f"No node with ID '{node_id}' found.")


def demo_run():
    net = Network(log_file="communication_log.txt")

    # Create nodes
    ceo = LLMNode("ceo", knowledge="Knows entire org structure.")
    marketing = LLMNode("marketing", knowledge="Knows about markets.")
    engineering = LLMNode("engineering", knowledge="Knows codebase.")
    design = LLMNode("design", knowledge="Knows UI/UX best practices.")

    # Register them
    net.register_node(ceo)
    net.register_node(marketing)
    net.register_node(engineering)
    net.register_node(design)

    # Start the CLI
    run_cli(net)


if __name__ == "__main__":
    demo_run()
