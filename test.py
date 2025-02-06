import openai
import json
from typing import Dict, Optional

# Set your OpenAI API key here or via environment variable
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
            print(f"Node {recipient_id} not found.")

    def _log_message(self, sender_id: str, recipient_id: str, content: str):
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"From {sender_id} to {recipient_id}: {content}\n")

class LLMNode:
    def __init__(self, node_id: str, knowledge: str = "", llm_api_key: str = "", llm_params: dict = None):
        self.node_id = node_id
        self.knowledge = knowledge
        self.llm_api_key = llm_api_key
        self.llm_params = llm_params if llm_params else {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        }

        # Each node can have short-term conversation memory:
        self.conversation_history = []
        # For multiple projects, store them in a dict:
        self.projects = {}  # { project_id: { "name": ..., "plan": [...], "participants": set(...) } }

        self.network: Optional[Network] = None

        if llm_api_key:
            openai.api_key = llm_api_key

    def receive_message(self, message: str, sender_id: str):
        # Step 4: conversation memory - store incoming message
        self.conversation_history.append({"role": "user", "content": f"{sender_id} says: {message}"})

        print(f"[{self.node_id}] Received message from {sender_id}: {message}")

        # Simple default response from LLM
        response = self.query_llm(self.conversation_history)

        # Store assistant response in memory
        self.conversation_history.append({"role": "assistant", "content": response})

        # Auto-reply to sender
        self.send_message(sender_id, response)

    def send_message(self, recipient_id: str, content: str):
        if not self.network:
            print(f"No network attached for node {self.node_id}.")
            return
        self.network.send_message(self.node_id, recipient_id, content)

    def query_llm(self, messages):
        """
        messages is a list of dicts: [{"role": "system", "content": ...}, {"role": "user", "content": ...}, ...]
        For simplicity, we'll build a system prompt + pass the user's conversation.
        """
        # Insert a system prompt at the start
        system_prompt = [{"role": "system", "content": "You are a helpful assistant for an organization."}]
        combined_messages = system_prompt + messages

        try:
            completion = openai.Chat.create(
                model=self.llm_params["model"],
                messages=combined_messages,
                temperature=self.llm_params.get("temperature", 0.7)
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[{self.node_id}] LLM query failed: {e}")
            return "LLM query failed."

    # Step 5: handle audio input
    def receive_audio(self, audio_file_path: str):
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript_data = openai.Audio.transcribe("whisper-1", audio_file)
            transcript_text = transcript_data["text"]
            print(f"[{self.node_id}] Transcribed audio: {transcript_text}")
            # treat as if user typed it
            self.receive_message(transcript_text, sender_id="audio_user")
        except Exception as e:
            print(f"[{self.node_id}] Audio transcription failed: {e}")

    # Step 7: orchestrate multiple projects
    def plan_project(self, project_id: str, objective: str):
        """
        We ask the LLM for a structured plan in JSON, then store it in self.projects[project_id]
        and notify relevant roles automatically.
        """
        if project_id not in self.projects:
            self.projects[project_id] = {
                "name": objective,
                "plan": [],
                "participants": set()
            }

        plan_prompt = f"""
        You are creating a project plan for project '{project_id}'.
        Objective: {objective}

        Return valid JSON with this structure:
        {{
          "plan": [
            {{
              "role": "string, e.g. 'marketing', 'engineering'",
              "action": "describe the next step",
              "details": "extra info"
            }}
          ]
        }}

        Do not add extra commentary outside the JSON.
        """

        # We'll pass only this plan_prompt to the LLM, ignoring conversation_history for clarity
        response = self.query_llm([{"role": "user", "content": plan_prompt}])
        print(f"[{self.node_id}] LLM raw response for project '{project_id}': {response}")

        # try to parse
        try:
            data = json.loads(response)
            plan_list = data.get("plan", [])
            self.projects[project_id]["plan"] = plan_list
            # auto-message relevant roles
            role_to_node = {
                "marketing": "marketing",
                "engineering": "engineering",
                "design": "design",
                "ceo": "ceo"
            }
            for item in plan_list:
                role = item.get("role", "").lower()
                action = item.get("action", "")
                details = item.get("details", "")
                if role in role_to_node:
                    self.send_message(role_to_node[role],
                                      f"Project '{project_id}' => Action: {action}\nDetails: {details}\nObjective: {objective}")
                    self.projects[project_id]["participants"].add(role_to_node[role])
                else:
                    print(f"[{self.node_id}] No mapping for role '{role}'. Skipping.")
        except json.JSONDecodeError as e:
            print(f"[{self.node_id}] Failed to parse JSON plan: {e}")

def run_cli(network):
    print("Type 'quit' to exit. Type 'help' for usage instructions.")
    while True:
        user_input = input("> ")
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "help":
            print("Commands:\n"
                  "  node_id: message (send 'message' to 'node_id')\n"
                  "  plan project (node_id: plan project_id = some_objective)\n"
                  "  quit (exit)\n")
            continue

        # Check if user wants to create a project plan
        # e.g., "ceo: plan p123 = Build an AI feature"
        if "plan" in user_input and "=" in user_input:
            try:
                node_part, plan_part = user_input.split("plan", 1)
                node_id = node_part.replace(":", "").strip()
                plan_part = plan_part.strip()
                project_id_part, objective_part = plan_part.split("=", 1)
                project_id = project_id_part.strip()
                objective = objective_part.strip()
                # call plan_project
                if node_id in network.nodes:
                    network.nodes[node_id].plan_project(project_id, objective)
                else:
                    print(f"No node found: {node_id}")
            except Exception as e:
                print(f"Error parsing plan command: {e}")
        else:
            # default: "node_id: message"
            if ":" not in user_input:
                print("Invalid format. Use 'node_id: message'.")
                continue
            node_id, message = user_input.split(":", 1)
            node_id = node_id.strip()
            message = message.strip()
            if node_id in network.nodes:
                network.nodes[node_id].receive_message(message, "cli_user")
            else:
                print(f"No node with ID '{node_id}' found.")


def demo_run():
    # create network
    net = Network(log_file="communication_log.txt")

    # create nodes
    ceo = LLMNode("ceo", knowledge="Knows entire org structure.")
    marketing = LLMNode("marketing", knowledge="Knows about markets.")
    engineering = LLMNode("engineering", knowledge="Knows codebase.")
    design = LLMNode("design", knowledge="Knows UI/UX best practices.")

    # register nodes
    net.register_node(ceo)
    net.register_node(marketing)
    net.register_node(engineering)
    net.register_node(design)

    # run CLI to demonstrate usage
    run_cli(net)

if __name__ == "__main__":
    demo_run()
