#!/usr/bin/env python3
import unittest
from unittest.mock import MagicMock, patch
from secretary.communication import Communication

class TestCommands(unittest.TestCase):
    def setUp(self):
        # Create mock objects
        self.mock_brain = MagicMock()
        self.mock_llm = MagicMock()
        self.mock_network = MagicMock()
        
        # Setup Communication class with the correct parameters
        self.comm = Communication(
            node_id="test_node",
            llm_client=self.mock_llm,
            network=self.mock_network,
            open_api_key="fake_api_key"
        )
        
        # Inject the brain after initialization
        self.comm.brain = self.mock_brain
        
    def test_list_tasks_command(self):
        # Setup mock return value
        self.mock_brain.list_tasks.return_value = "Task 1\nTask 2"
        
        # Test the command
        result = self.comm._handle_quick_command("tasks", "cli_user")
        
        # Verify brain.list_tasks was called
        self.mock_brain.list_tasks.assert_called_once()
        self.assertEqual(result, "Task 1\nTask 2")
        
    def test_plan_project_command(self):
        # Setup mock return value
        self.mock_brain.plan_project.return_value = "Project planned successfully"
        
        # Test the command with the original syntax
        result = self.comm._handle_quick_command("plan project-x = Build a website", "cli_user")
        
        # Verify brain.plan_project was called with correct args
        self.mock_brain.plan_project.assert_called_with("project-x", "Build a website")
        self.assertEqual(result, "Project planned successfully")
        
    def test_create_project_command(self):
        # Setup mock return value
        self.mock_brain.plan_project.return_value = "Project planned successfully"
        
        # Test the command with the alternative syntax
        result = self.comm._handle_quick_command("create project project-y Build a mobile app", "cli_user")
        
        # Verify brain.plan_project was called with correct args
        self.mock_brain.plan_project.assert_called_with("project-y", "Build a mobile app")
        self.assertEqual(result, "Project planned successfully")
        
    def test_generate_tasks_command(self):
        # Setup mocks and project data
        project_id = "project-z"
        self.mock_brain.projects = {
            project_id: {
                "plan": ["step1", "step2"],
                "participants": {"ceo", "engineering"}
            }
        }
        
        # Test the command
        result = self.comm._handle_quick_command(f"generate tasks for {project_id}", "cli_user")
        
        # Verify brain.generate_tasks_from_plan was called with correct args
        self.mock_brain.generate_tasks_from_plan.assert_called_with(
            project_id, 
            ["step1", "step2"], 
            ["ceo", "engineering"]
        )
        self.assertEqual(result, f"Tasks generated for project '{project_id}'.")
        
    def test_nonexistent_project(self):
        # Setup empty projects dict
        self.mock_brain.projects = {}
        
        # Test command with nonexistent project
        result = self.comm._handle_quick_command("generate tasks for nonexistent", "cli_user")
        
        # Verify the error message
        self.assertEqual(
            result, 
            "Project 'nonexistent' does not exist. Please create it first with 'plan nonexistent=<objective>'."
        )
        
    def test_project_without_steps(self):
        # Setup project without steps
        project_id = "empty-project"
        self.mock_brain.projects = {
            project_id: {
                "plan": [],
                "participants": {"ceo"}
            }
        }
        
        # Test command
        result = self.comm._handle_quick_command(f"generate tasks for {project_id}", "cli_user")
        
        # Verify the error message
        self.assertEqual(
            result,
            f"Project '{project_id}' has no steps defined. Please create a plan first."
        )

if __name__ == "__main__":
    unittest.main() 