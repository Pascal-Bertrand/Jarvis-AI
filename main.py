from openai import OpenAI
from typing import Dict, Optional
import json


client = OpenAI(api_key="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")

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
    """
    Represents a user within the organization, each with their own LLM instance
    and associated knowledge base.
    """
    def __init__(self, node_id: str, knowledge: str = "", llm_api_key: str = "", llm_params: dict = None):
        """
        :param node_id: A unique identifier for the user (e.g., 'ceo', 'marketing', etc.)
        :param knowledge: A placeholder for the user's knowledge/documents (text for prototype).
        :param llm_api_key: The API key for OpenAI or other LLM providers.
        :param llm_params: Dict of parameters for the LLM, e.g. {"model": "gpt-3.5-turbo", "temperature": 0.7}.
        """
        self.node_id = node_id
        self.knowledge = knowledge
        self.llm_api_key = llm_api_key
        self.llm_params = llm_params if llm_params is not None else {
            "model": "gpt-3.5-turbo",
            "temperature": 0.9
        }

        self.network: Optional[Network] = None

        # Set the API key (minimal approach, all nodes might share the same key for the prototype)
        if llm_api_key:
            openai.api_key = llm_api_key

    def receive_message(self, message: str, sender_id: str):
        """
        Called by the Network when a message arrives.
        We can feed the message + the node's knowledge into the LLM to generate a response or an action.
        """
        print(f"[{self.node_id}] Received message from {sender_id}: {message}")

        # For demonstration, the node might generate a short LLM-based response:
        response = self.query_llm(f"User {sender_id} says: {message}\n\n"
                                  f"My knowledge: {self.knowledge}\n\n"
                                  "Compose a short helpful reply or next step.")
        # Optionally send a reply back to the sender:
        self.send_message(sender_id, response)

    def send_message(self, recipient_id: str, content: str):
        """
        Send a message to another node via the network.
        """
        if self.network is None:
            raise ValueError("LLMNode is not attached to a network.")
        self.network.send_message(self.node_id, recipient_id, content)

    def query_llm(self, prompt: str) -> str:
        """
        Send a prompt to the OpenAI ChatCompletion endpoint (or a future LLM call).
        """
        try:
            completion = client.chat.completions.create(
                messages=[{"role": "system", "content": "You are a helpful assistant."},
                          {"role": "user", "content": prompt}],
                **self.llm_params
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[{self.node_id}] LLM query failed: {e}")
            return "LLM query failed."

    def plan_project(self, objective: str):
        """
        Instruct the LLM to create a structured plan in JSON.
        Then parse the plan and automatically message the relevant nodes.
        """

        # 1. Define a JSON structure in the prompt
        plan_prompt = f"""
        You are creating a project plan for the following objective:
        {objective}

        Return your answer in valid JSON with the following structure:
        {{
          "plan": [
            {{
              "role": "string, e.g. 'marketing' or 'engineering'",
              "action": "string describing the action to be taken",
              "details": "additional context or info about this step"
            }},
            ...
          ]
        }}
        Only return valid JSON, no extra commentary.
        """

        # 2. Query the LLM
        response = self.query_llm(plan_prompt)
        print(f"[{self.node_id}] LLM raw response:\n{response}\n")

        # 3. Parse the JSON
        try:
            data = json.loads(response)
            plan_list = data.get("plan", [])

            print(f"[{self.node_id}] Parsed plan: {plan_list}")

            # 4. For demonstration, define how to map roles to node_ids
            role_to_node = {
                "marketing": "marketing",
                "engineering": "engineering",
                "design": "design",
                "ceo": "ceo"  # If needed
            }

            # 5. Loop over the plan items and send messages
            for item in plan_list:
                role = item.get("role", "").lower()
                action = item.get("action", "")
                details = item.get("details", "")

                if role in role_to_node:
                    target_node = role_to_node[role]

                    # Construct a message to the target
                    message_text = (
                        f"New action item for '{role}':\n"
                        f"Action: {action}\n"
                        f"Details: {details}\n"
                        f"Objective: {objective}\n"
                    )

                    # Send the message to the appropriate LLM node
                    self.send_message(target_node, message_text)
                else:
                    print(f"[{self.node_id}] No mapping for role '{role}'. Skipping.")

        except json.JSONDecodeError as e:
            print(f"[{self.node_id}] Error: Could not parse LLM response as JSON.\n{e}")


def demo_run():
    net = Network(log_file="communication_log.txt")

    ceo = LLMNode(node_id="ceo", knowledge="Knows the entire org structure.")
    marketing = LLMNode(node_id="marketing", knowledge="Knows about markets.")
    engineering = LLMNode(node_id="engineering", knowledge="Knows about product code.")
    design = LLMNode(node_id="design", knowledge="Knows about UI/UX.")

    net.register_node(ceo)
    net.register_node(marketing)
    net.register_node(engineering)
    net.register_node(design)

    # CEO starts a new project, automatically triggering a plan, which dispatches messages
    ceo.plan_project("Build a new AI-powered feature for our main product.")


if __name__ == "__main__":
    demo_run()
