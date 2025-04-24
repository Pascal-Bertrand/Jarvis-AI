from network.internal_communication import Intercom
from network.tasks import Task
from main import LLMNode   # or wherever you keep your node logic

def demo_run():
    network = Intercom()
    # create and register nodes:
    for node_id in ["ceo", "marketing", "engineering", "design"]:
        node = LLMNode(node_id)
        network.register_node(node_id, node)

    # now networking, messaging, tasks all work without network code knowing about LLMNode

if __name__ == "__main__":
    demo_run()
    # run tests here or in a separate test file
    # e.g., pytest or unittest framework can be used to run the tests
    # pytest tests/test_network.py
    # or use unittest framework to create a test suite and run it
