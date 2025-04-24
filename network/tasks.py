from typing import Dict, Any
import datetime
import uuid

class Task:
    """
    Represents a work item assigned to a participant in the network.
    
    Each Task encapsulates everything needed to track and notify about a discrete unit of work.
    
    Attributes:
        id (str):
            A globally unique identifier for the task, generated via UUID4.
        title (str):
            A brief, human-readable summary of the task’s goal.
        description (str):
            A detailed explanation of what needs to be done.
        due_date (datetime.datetime):
            The deadline by which the task should be completed.
        assigned_to (str):
            The node_id of the network participant responsible for this task.
        priority (str):
            The importance level, e.g. 'high', 'medium', or 'low'.
        project_id (str):
            Identifier linking this task back to a broader project context.
        completed (bool):
            Flag indicating whether the task has been finished.
    """
  
    def __init__(self, title: str, description: str, due_date: datetime.datetime, assigned_to: str, priority: str, project_id: str):
          
        # Generate a unique ID for this task
        self.id: str = uuid.uuid4().hex
        # Short summary of the task
        self.title: str = title
        # Detailed instructions or context
        self.description: str = description
        # Deadline for completion
        self.due_date: datetime.datetime = due_date
        # Node responsible for this task
        self.assigned_to: str = assigned_to
        # Importance level of the task
        self.priority: str = priority
        # Link back to the overall project
        self.project_id: str = project_id
        # Completion status flag
        self.completed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert this Task into a JSON-serializable dictionary.

        Returns:
            A dict containing all Task attributes, with due_date as an ISO-formatted string.
        """
      
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date.isoformat(),
            "assigned_to": self.assigned_to,
            "priority": self.priority,
            "project_id": self.project_id,
            "completed": self.completed,
        }

    def __str__(self) -> str:
        """
        Return a concise, human-readable summary of the task,
        including title, due date, priority, and assignee.
        """
      
        date_str = self.due_date.strftime('%Y-%m-%d')
        return f"{self.title} (Due: {date_str}) [Priority: {self.priority}] → {self.assigned_to}"

#TODO: Add more functionalities
