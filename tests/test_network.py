from network.internal_communication import Intercom
from network.tasks import Task
from your_node_module import LLMNode   # or wherever you keep your node logic

def demo_run():
    network = Intercom()
    # create and register nodes:
    for node_id in ["ceo", "marketing", "engineering", "design"]:
        node = LLMNode(node_id, …)
        network.register_node(node_id, node)

    # now networking, messaging, tasks all work without network code knowing about LLMNode
    …
