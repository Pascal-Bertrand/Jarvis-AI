from people import People

class Intercom(People):
    """
    Represents the communication part of a network that connects various agents.
    
    Attributes:
        nodes (Dict[str, LLMNode]): A dictionary that maps node IDs to node instances.
        log_file (Optional[str]): Path to a log file where messages will be recorded. If None, logging is disabled.
        tasks (List[Task]): A list that stores tasks assigned to nodes.
    """

    def send_message(self, sender_id: str, recipient_id: str, content: str):
        """
        Send a message from one node to another.
        
        This function first logs the outgoing message by calling a private logging function.
        Then, it checks if the recipient exists in the network's nodes dictionary:
          - If the recipient exists, the message is delivered by invoking the recipient's 'receive_message' method.
          - If the recipient does not exist, an error message is printed.
        
        Args:
            sender_id (str): Identifier of the node sending the message.
            recipient_id (str): Identifier of the recipient node.
            content (str): The message content to be transmitted.
            
        The function ensures that every message is logged and that message delivery occurs only if the
        target node is registered in the network.
        """

        # Log the message regardless of whether the recipient exists.
        self._log_message(sender_id, recipient_id, content)

        # Send the message if the recipient exists in the network's node list.
        if recipient_id in self.nodes:
            self.nodes[recipient_id].receive_message(content, sender_id)
        else:
            # Print an error message if recipient is not found.
            print(f"Node {recipient_id} not found in the network.")

    def _log_message(self, sender_id: str, recipient_id: str, content: str):
        """
        Log a message to a file if logging is enabled.
        
        This private helper method writes the details of the message in a formatted string to the
        specified log file. It appends the message so that previous logs are preserved.
        
        Args:
            sender_id (str): The identifier of the node that originated the message.
            recipient_id (str): The identifier of the target node.
            content (str): The textual content of the message.
            
        If no log file is specified (i.e., log_file is None), the message is not logged.
        """
        
        # Log using our new logging module
        log_network_message(sender_id, recipient_id, content)
        
        # Also preserve original file logging if configured
        if self.log_file:
            # Open the log file in append mode with UTF-8 encoding to handle any special characters.
            with open(self.log_file, "a", encoding="utf-8") as f:
                # Write the message in a readable format.
                f.write(f"From {sender_id} to {recipient_id}: {content}\n")

    def add_task(self, task: Task):
        """
        Add a new task to the network and notify the assigned node.
        
        The task is appended to the network's task list. If the task has an assigned node (its 'assigned_to' attribute
        corresponds to a registered node), the method constructs a notification message detailing the task's title,
        due date, and priority, and then sends this message from a system-generated sender.
        
        Args:
            task (Task): A task object with at least the following attributes:
                        - title (str): A brief description or title of the task.
                        - due_date (datetime): A datetime object representing the task's deadline.
                        - priority (Any): The priority level of the task.
                        - assigned_to (str): The node ID of the node to which the task is assigned.
                        
        This approach immediately informs the responsible node of new task assignments, which is critical
        for task management in networked applications.
        """
        
        self.tasks.append(task) # Add the new task to the list.
        
        # Build a notification message with task details.
        if task.assigned_to in self.nodes:
            message = f"New task assigned: {task.title}. Due: {task.due_date.strftime('%Y-%m-%d')}. Priority: {task.priority}."

            # Send the notification message from a system-originated sender.
            self.send_message("system", task.assigned_to, message)
    
    def get_tasks_for_node(self, node_id: str) -> List[Task]:
        """
        Retrieve all tasks assigned to a given node.
        
        This method filters the list of tasks and returns only those tasks where the 'assigned_to' attribute
        matches the provided node_id. This allows a node (or any client) to query for tasks specifically targeted to it.
        
        Args:
            node_id (str): The identifier of the node for which to fetch assigned tasks.
        
        Returns:
            List[Task]: A list of task objects that have been assigned to the node with the given node_id.
        """

        # Use a list comprehension to filter tasks by comparing the assigned_to attribute.
        return [task for task in self.tasks if task.assigned_to == node_id]

#TODO: Add more functionalities
