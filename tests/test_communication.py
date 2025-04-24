import pytest
import base64

# Import the module under test
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
        self.plan_calls = []  # record plan_project calls

    def plan_project(self, project_id, objective):
        self.plan_calls.append((project_id, objective))

    def _detect_send_email_intent(self, message):
        # By default, indicate no email send intent
        return {'is_send_email': False, 'action': 'none', 'missing_info': []}

    def process_advanced_email_command(self, message):
        return f"advanced_processed: {message}"

    def query_llm(self, conversation_history):
        return "llm_response"
    
    def list_tasks(self):
        return "No tasks assigned to brain"

@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    """
    Automatically patch out:
    - Google service initialization
    - Scheduler and Brain classes
    """
    monkeypatch.setattr(communication, 'initialize_google_services', lambda node_id: {'calendar': None, 'gmail': None})
    monkeypatch.setattr(communication, 'Scheduler', FakeScheduler)
    monkeypatch.setattr(communication, 'Brain', FakeBrain)

# --- Tests for quick CLI commands ---
def test_handle_quick_command_tasks(capsys):
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    # Override FakeBrain.list_tasks to return a known string
    comm.brain.list_tasks = lambda: "No tasks assigned to brain"

    # CLI user invokes 'tasks'
    assert comm._handle_quick_command('tasks', 'cli_user') is True

    captured = capsys.readouterr()
    # Confirm that exactly the stubbed string is printed
    assert "[node1] Response: No tasks assigned to brain" in captured.out

def test_handle_quick_command_plan():
    """
    When CLI user sends 'plan project = objective',
    verify that Brain.plan_project was called with correct args.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    result = comm._handle_quick_command('plan myproj = Do something important', 'cli_user')
    assert result is True

    # Check that FakeBrain recorded the call
    assert comm.brain.plan_calls == [('myproj', 'Do something important')]

def test_handle_quick_command_non_cli():
    """
    Non-CLI sender should not trigger quick commands.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    assert not comm._handle_quick_command('tasks', 'other')

# --- Tests for calendar delegation in receive_message() ---
def test_calendar_delegation():
    """
    If scheduler._detect_calendar_intent returns True,
    receive_message should delegate entirely to handle_calendar().
    """
    class CalScheduler(FakeScheduler):
        def _detect_calendar_intent(self, message):
            return {'is_calendar_command': True}
        def handle_calendar(self, intent, message):
            return "calendar_result"

    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.scheduler = CalScheduler('node1', None)
    comm.brain = FakeBrain('node1', 'key', None)  # ensure no email intercept
    res = comm.receive_message('irrelevant text', 'someone')
    assert res == "calendar_result"

# --- Tests for advanced email command handling ---
def test_advanced_email_processing(capsys):
    """
    When Brain indicates an advanced email action (action != 'none'),
    receive_message should call process_advanced_email_command and print its response.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    # Force no calendar command
    comm.scheduler._detect_calendar_intent = lambda msg: {'is_calendar_command': False}
    # Force an email action
    comm.brain._detect_send_email_intent = lambda msg: {'is_send_email': False, 'action': 'do_email', 'missing_info': []}
    comm.brain.process_advanced_email_command = lambda msg: "email_done"

    comm.receive_message('Please do this email', 'other')
    captured = capsys.readouterr()
    assert "Response: email_done" in captured.out

# --- Tests for fallback to LLM chat ---
def test_fallback_to_llm(capsys):
    """
    If no calendar or email intents, receive_message should fall back to LLM chat.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.scheduler._detect_calendar_intent = lambda msg: {'is_calendar_command': False}
    comm.brain._detect_send_email_intent = lambda msg: {'is_send_email': False, 'action': 'none'}
    
    def fake_chat(msg):
        # Simulate LLM response
        print(f"[node1] Response: chat_fallback")
        return "chat_fallback"
    
    comm._chat_with_llm = fake_chat


    result = comm.receive_message('Hello there', 'someone')
    assert result == "chat_fallback"

    captured = capsys.readouterr()
    assert "Response: chat_fallback" in captured.out

# --- Tests for _extract_email_body() ---
def test_extract_email_body_simple():
    """
    Single-part payload: base64 data should decode correctly.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    data = base64.urlsafe_b64encode(b'hello').decode()
    payload = {'body': {'data': data}}
    assert comm._extract_email_body(payload) == 'hello'

def test_extract_email_body_multipart():
    """
    Multipart payload: prefer text/plain, then html.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    plain = base64.urlsafe_b64encode(b'plain').decode()
    html = base64.urlsafe_b64encode(b'<p>html</p>').decode()
    # Case 1: both present → plain
    payload = {'parts': [
        {'mimeType': 'text/plain', 'body': {'data': plain}},
        {'mimeType': 'text/html', 'body': {'data': html}}
    ]}
    assert comm._extract_email_body(payload) == 'plain'
    # Case 2: only html → html
    payload2 = {'parts': [
        {'mimeType': 'text/html', 'body': {'data': html}}
    ]}
    assert comm._extract_email_body(payload2) == '<p>html</p>'

def test_extract_email_body_empty():
    """
    No body or parts → returns placeholder.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    assert comm._extract_email_body({}) == '(No content)'

# --- Tests for fetch_emails() ---
def test_fetch_emails_no_service(capsys):
    """
    If gmail_service is None, fetch_emails should print a warning and return [].
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')
    comm.gmail_service = None
    emails = comm.fetch_emails()
    assert emails == []
    captured = capsys.readouterr()
    assert "Gmail service not available" in captured.out

def test_fetch_emails_with_service(capsys):
    """
    When a fake Gmail service is provided, fetch_emails should
    list, get, decode, and return emails correctly.
    """
    comm = communication.Communication('node1', llm_client=None, network=None, open_api_key='key')

    class FakeGmailService:
        def users(self): return self
        def messages(self): return self

        def list(self, userId, q, maxResults):
            class R:
                def execute(inner):
                    return {'messages': [{'id': 'id1'}]}
            return R()

        def get(self, userId, id, format):
            class G:
                def execute(inner):
                    return {
                        'id': 'id1',
                        'payload': {
                            'headers': [
                                {'name': 'Subject', 'value': 'Test'},
                                {'name': 'From',    'value': 'sender@example.com'},
                                {'name': 'Date',    'value': '2025-04-24'}
                            ],
                            'body': {'data': base64.urlsafe_b64encode(b'body text').decode()}
                        },
                        'snippet':  'snippet text',
                        'labelIds': ['LABEL_1']
                    }
            return G()

    comm.gmail_service = FakeGmailService()
    emails = comm.fetch_emails(max_results=1, query='test')

    # Validate the structure and content of the returned email
    assert isinstance(emails, list) and len(emails) == 1
    email = emails[0]
    assert email['id'] == 'id1'
    assert email['subject'] == 'Test'
    assert email['sender'] == 'sender@example.com'
    assert email['date'] == '2025-04-24'
    assert email['body'] == 'body text'
    assert email['snippet'] == 'snippet text'
    assert email['labelIds'] == ['LABEL_1']

    captured = capsys.readouterr()
    assert "Fetched 1 emails" in captured.out
