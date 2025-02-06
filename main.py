import openai
import os
from typing import Dict, Optional
OPENAI_API_KEY="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"


class Network:
    """
    The Network class manages communication between LLMNode instances.
    It can optionally log all messages to a text file.
    """
    def __init__(self, log_file: Optional[str] = None):
        self.nodes: Dict[str, 'LLMNode'] = {}
        self.log_file = log_file

    def register_node(self, node: 'LLMNode'):
        self.nodes[node.node_id] = node
        node.network = self

    def send_message(self, sender_id: str, recipient_id: str, content: str):
        """
        Deliver a message from sender to recipient. Also log the exchange if a log file is specified.
        """
        # Log the message
        self._log_message(sender_id, recipient_id, content)

        # Deliver the message
        recipient_node = self.nodes.get(recipient_id)
        if recipient_node:
            recipient_node.receive_message(content, sender_id)
        else:
            print(f"Node {recipient_id} not found in the network.")

    def _log_message(self, sender_id: str, recipient_id: str, content: str):
        """
        Append the message to a log file if specified.
        """
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
            "temperature": 0.7
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
            completion = openai.ChatCompletion.create(
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
        An example method to show how this node can leverage LLM logic to plan
        a project and potentially involve other nodes.
        """
        prompt = f"Objective: {objective}\n\n"
        plan = self.query_llm(prompt + 
                              "Please propose a step-by-step plan, including which roles/people to involve.")
        print(f"[{self.node_id}] Proposed plan:\n{plan}")
        # Here, you could parse the plan to identify relevant people and send messages automatically.
        # For now, just printing it out.


def demo_run():
    # Suppose we have a network for our small organization
    net = Network(log_file="communication_log.txt")

    # Create a few LLMNodes with some minimal knowledge
    ceo = LLMNode(node_id="ceo", knowledge="Knows about the entire org. Key players: marketing, engineering, design.")
    marketing = LLMNode(node_id="marketing", knowledge="Knows about market trends and customer needs.")
    engineering = LLMNode(node_id="engineering", knowledge="Knows about product technical details and code base.")
    design = LLMNode(node_id="design", knowledge="Knows about user interfaces and design best practices.")

    # Register them with the network
    net.register_node(ceo)
    net.register_node(marketing)
    net.register_node(engineering)
    net.register_node(design)

    # Demonstration: The CEO wants to start a new project
    ceo.plan_project("Build a new AI-powered feature for our main product.")

    # CEO manually decides to reach out to the marketing team
    ceo.send_message("marketing", "Hey marketing, we are starting a new AI feature. Let's brainstorm positioning.")


if __name__ == "__main__":
    demo_run()
