from typing import Optional, Dict, List, Any
import datetime

from network.tasks import Task

class People:
    """
    Manages a registry of participants and their shared tasks.
    
    Attributes:
        nodes (Dict[str, object]): Maps participant IDs to participant objects, which must implement a receive_message(content: str, sender_id: str) method.
        log_file (Optional[str]): Path to an optional log file for message persistence (used by subclasses).
        tasks (List[Task]): List of Task instances tracked by the network; populated by subclasses.
    """
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize the People registry.
        
        Args:
            log_file (Optional[str]): The file path for logging messages. If provided, every message
                                      sent through the network will be appended to this file.
        
        Initializes:
            - self.nodes: empty dict for participant registration
            - self.log_file: stored file path for logging
            - self.tasks: empty list for tasks (managed by subclasses)
        """
  
        # Map of participant_id to participant instance
        self.nodes: Dict[str, object] = {}
        # Optional path for logging activity file
        self.log_file = log_file
        # Shared task list; actual addition happens via subclass methods (in particular Intercom)
        self.tasks: List[Task] = []
        
    def register_node(self, node_id: str, node_obj: object):
        """
        Register a new participant in the network.
        
        Stores node_obj under the given node_id and sets a back-reference for messaging.
        
        Args:
            node_id: Unique identifier for the participant.
            node_obj: Participant object, which must provide a receive_message method.
        """
        
        self.nodes[node_id] = node_obj
        # Give the node a back-pointer
        setattr(node_obj, 'network', self)
  
    def unregister_node(self, node_id: str):
        """
        Remove a participant from the network, if present.
        
        Clears its back-reference and deletes its entry from nodes.
        
        Args:
            node_id: Identifier of the participant to remove.
        """
      
        node = self.nodes.pop(node_id, None)
        if node:
            # Clear the back-reference
            setattr(node, 'network', None)


    def get_all_nodes(self) -> List[str]:
        """
        Retrieve a list of all registered participant IDs.
        
        Returns:
            A list of node_id strings currently in the network.
        """

        return list(self.nodes.keys())


# The Network class below is removed as it's redundant after refactoring.
# Intercom is used directly in main.py, and it inherits from People.
# class Network(People):
#     def __init__(self, log_file: Optional[str] = None):
#         super().__init__(log_file)
#
#     def register_node(self, node: LLMNode): # This caused NameError
#         """
#         Register a node with the network.
#
#         This method adds the node to the network's internal dictionary using the node's unique identifier.
#         It also sets the node's 'network' attribute to reference this Network instance, establishing a two-way link.
#
#         Args:
#             node (LLMNode): The node instance to register. The node must have a 'node_id' attribute.
#         """
#         super().register_node(node.node_id, node)


#TODO: Add more functionalities.
