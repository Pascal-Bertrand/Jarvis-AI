from typing import List

from network.people import People
from network.tasks import Task
from secretary.utilities.logging import log_network_message

class Intercom(People):
    """
    Manages message passing and task notifications among registered participants.
    
    Attributes:
        nodes (Dict[str, object]): Mapping of node IDs to participant objects that implement a receive_message(content: str, sender_id: str) method.
        log_file (Optional[str]): Path to a log file where messages will be recorded. If None, logging is disabled.
        tasks (List[Task]): A list of Task instances tracked by the network.
    """

    def send_message(self, sender_id: str, recipient_id: str, content: str) -> None:
        """
        Dispatch a message from one participant to another, logging each attempt.
        
        Logs the message first, then attempts delivery only if the recipient is registered.
        If the recipient is not found, prints a warning instead of raising an error.
        
        Args:
            sender_id (str): ID of the sending participant.
            recipient_id (str): ID of the intended recipient.
            content (str): The message payload to deliver.
        """

        # Log the message regardless of whether the recipient exists.
        self._log_message(sender_id, recipient_id, content)

        # Returns "recipient_id" if the node exists and "None" if it doesn't
        recipient = self.nodes.get(recipient_id)

        # Send the message if the recipient exists in the network's node list. Note: The if-statement checks for empty/non-empty
        if recipient:
            recipient.receive_message(content, sender_id)
        else:
            # Print an error message if recipient is not found.
            print(f"[Intercom] Unknown recipient: {recipient_id}.")

    def _log_message(self, sender_id: str, recipient_id: str, content: str) -> None:
        """
        Record a network message using the external logging utility and the internal logging (if enabled.
        
        Args:
            sender_id (str): Originating participant ID.
            recipient_id (str): Target participant ID.
            content (str): Message content for logging.
        """
        
        # Log using external logging module
        log_network_message(sender_id, recipient_id, content)

        #----------------Note: We can probably remove the logging inside the network------------------#
        
        # Also preserve original file logging if configured
        if self.log_file:
            # Open the log file in append mode with UTF-8 encoding to handle any special characters.
            with open(self.log_file, "a", encoding="utf-8") as f:
                # Write the message in a readable format.
                f.write(f"From {sender_id} to {recipient_id}: {content}\n")

    def add_task(self, task: Task):
        """
        Add a Task to the network and notify its assignee if registered.
        
        Appends the task to self.tasks. If task.assigned_to matches a registered node,
        constructs a notification string and sends it from a pseudo-sender "system".
        
        Args:
            task (Task): A task object with at least the following attributes:
                        - title (str): A brief description or title of the task.
                        - due_date (datetime): A datetime object representing the task's deadline.
                        - priority (Any): The priority level of the task.
                        - assigned_to (str): The node ID of the node to which the task is assigned.
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
