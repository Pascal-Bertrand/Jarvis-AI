from typing import Optional, Dict, List, Any
import datetime

class People:
    """
    Represents a network that connects various agents. 
      
      Attributes:
          nodes (Dict[str, LLMNode]): A dictionary that maps node IDs to node instances.
    """
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize a new Network instance.
        
        Args:
            log_file (Optional[str]): The file path for logging messages. If provided, every message
                                      sent through the network will be appended to this file.
                                      
        The constructor sets up:
         - an empty dictionary 'nodes' to store registered nodes,
         - a log file path (if any),
         - an empty list 'tasks' to track tasks in the network.
        """
  
        # Object can be any object with .receive_message (more general than the previously used LLMNode)
        self.nodes: Dict[str, object] = {}
        self.log_file = log_file
        self.tasks: List[Task] = []
        
    def register_node(self, node_id: str, node_obj: object):
        """
        Register a node with the network.
        
        This method adds the node to the network's internal dictionary using the node's unique identifier.
        It also sets the node's 'network' attribute to reference this Network instance, establishing a two-way link.
        
        Args:
            node (LLMNode): The node instance to register. The node must have a 'node_id' attribute.
            
        After registration, the node can participate in messaging and task management within the network.
        """
        
        self.nodes[node_id] = node_obj
        # Give the node a back-pointer
        setattr(node_obj, 'network', self)
  
    def unregister_node(self, node_id: str):
        """
        Remove participant (silent if unknown).
        """
      
        if node_id in self.nodes:
            self.nodes[node_id].network = None
            del self.nodes[node_id]


    def get_all_nodes(self) -> List[str]:
        """
        Return a list of node IDs.
        """

        return list(self.nodes.keys())


#TODO: Add more functionalities.
