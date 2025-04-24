class people:
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
      """
      
      self.nodes: Dict[str, LLMNode] = {}

    def register_node(self, node: 'LLMNode'):
        """
        Register a node with the network.
        
        This method adds the node to the network's internal dictionary using the node's unique identifier.
        It also sets the node's 'network' attribute to reference this Network instance, establishing a two-way link.
        
        Args:
            node (LLMNode): The node instance to register. The node must have a 'node_id' attribute.
            
        After registration, the node can participate in messaging and task management within the network.
        """
        
        self.nodes[node.node_id] = node
        node.network = self


#TODO: Add more functionalities.
