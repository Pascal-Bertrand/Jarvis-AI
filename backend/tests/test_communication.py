import pytest

import secretary.communication as communication

# --- Mocks to stub out external dependencies ---
class FakeScheduler:
    """Stubs calendar intent detection and handling."""
    def __init__(self, node_id, calendar_service):
        self.node_id = node_id
        self.calendar_service = calendar_service

    def _detect_calendar_intent(self, message):
        return {'is_calendar_command': False}

    def handle_calendar(self, intent, message):
        return f"handled_calendar: {message}"

class FakeBrain:
    """Stubs project planning, email intent detection, and LLM chat."""
    def __init__(self, node_id, open_api_key, network, llm_params=None, socketio_instance=None):
        self.node_id = node_id
        self.open_api_key = open_api_key
        self.network = network
        self.plan_calls = []

    def plan_project(self, project_id, objective):
        self.plan_calls.append((project_id, objective))
        return f"Planned {project_id}"

    def _analyze_email_command(self, message):
        return {'action': 'none'}

    def _detect_send_email_intent(self, message):
        return {'is_send_email': False, 'action': 'none', 'missing_info': []}

    def process_advanced_email_command(self, analysis):
        return f"advanced_processed: {analysis}"

    def query_llm(self, conversation_history):
        return "llm_response"

    def list_tasks(self):
        return "No tasks assigned to brain"

# --- Tests for quick CLI commands ---

def test_handle_quick_command_tasks():
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.brain = FakeBrain('node1', 'key', None)
    comm.brain.list_tasks = lambda: "No tasks here"

    res = comm._handle_quick_command('tasks', 'cli_user')
    assert res == "No tasks here"


def test_handle_quick_command_plan():
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.brain = FakeBrain('node1', 'key', None)

    res = comm._handle_quick_command('plan myproj = Do something important', 'cli_user')
    assert res == "Planned myproj"
    assert comm.brain.plan_calls == [('myproj', 'Do something important')]


def test_handle_quick_command_non_cli():
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.brain = FakeBrain('node1', 'key', None)

    res = comm._handle_quick_command('tasks', 'other')
    assert res is None

# --- Tests for advanced email command handling ---

def test_advanced_email_processing():
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.brain = FakeBrain('node1', 'key', None)

    # Ensure email keywords trigger email logic
    message = 'Please list my email labels'
    comm.brain._analyze_email_command = lambda msg: {'action': 'list_labels'}
    comm.brain.process_advanced_email_command = lambda analysis: "labels_listed"

    res = comm.receive_message(message, 'user')
    assert res == "labels_listed"

# --- Tests for fallback to LLM chat ---

def test_fallback_to_llm():
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.brain = FakeBrain('node1', 'key', None)

    # No email keywords and no CLI command should fall back
    comm.brain._detect_send_email_intent = lambda msg: {'is_send_email': False, 'action': 'none', 'missing_info': []}
    comm._chat_with_llm = lambda message: "chat_fallback"

    result = comm.receive_message('Hello there', 'someone')
    assert result == "chat_fallback"
