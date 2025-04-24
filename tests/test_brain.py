import json
import pytest
from datetime import datetime, timedelta

import openai

from secretary.brain import LLMClient, Confirmation, Brain
from network.internal_communication import Intercom
from network.tasks import Task

class DummyChatCompletion:
    def __init__(self, response_text):
        self.response_text = response_text

    def create(self, model, messages, temperature, max_tokens):
        class Choice:
            def __init__(self, text):
                self.message = type('M', (), {'content': text})
        return type('R', (), {'choices': [Choice(self.response_text)]})


@pytest.fixture(autouse=True)
def patch_openai(monkeypatch):
    """Monkeypatch openai.ChatCompletion for LLMClient and other raw calls."""
    dummy = DummyChatCompletion("dummy reply")
    monkeypatch.setattr(openai, 'ChatCompletion', dummy)
    yield


def test_llmclient_chat_success():
    params = {"model": "test-model", "temperature": 0.5, "max_tokens": 10}
    client = LLMClient("key", params)

    # Should return dummy reply from our DummyChatCompletion
    res = client.chat([{"role": "user", "content": "hi"}])
    assert res == "dummy reply"


def test_confirmation_yes(monkeypatch):
    conf = Confirmation()
    monkeypatch.setattr('builtins.input', lambda prompt: 'y')
    assert conf.request("Proceed?") is True


def test_confirmation_no(monkeypatch):
    conf = Confirmation()
    monkeypatch.setattr('builtins.input', lambda prompt: 'n')
    assert conf.request("Proceed?") is False


class DummyLLM:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.outputs.pop(0)


@pytest.fixture
def brain():
    net = Intercom()
    b = Brain("brain", "key", net, llm_params={"model": "m", "temperature": 0, "max_tokens": 1})
    # swap out the client wrapper for dummy
    b.llm = DummyLLM(["{\"foo\":\"bar\"}", "response"])
    return b


def test_extract_meeting_details_defaults(brain):
    # llm.chat returns JSON without date/time
    brain.llm = DummyLLM(['{"title":"T","participants":["a","b"],"date":"","time":"","duration":30}'])
    res = brain._extract_meeting_details("msg")
    assert res["title"] == "T"
    assert res["participants"] == ["a", "b"]
    # default date is today
    assert res["date"] == datetime.now().strftime("%Y-%m-%d")
    # default time is +1h
    expected_time = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
    assert res["time"] == expected_time
    assert res["duration"] == 30


def test_extract_meeting_details_error(brain):
    # simulate exception in chat
    class BadLLM:
        def chat(self, messages):
            raise RuntimeError("fail")
    brain.llm = BadLLM()
    res = brain._extract_meeting_details("msg")
    assert res == {}


def test_query_llm_and_logging(brain):
    # llm.chat returns "ok"
    brain.llm = DummyLLM(["ok"])
    resp = brain.query_llm([{"role": "user", "content": "test"}])
    assert resp == "ok"


def test_list_tasks_empty(brain):
    # no tasks assigned
    tasks_str = brain.list_tasks()
    assert "No tasks assigned to brain" in tasks_str


def test_list_tasks_with_tasks(brain):
    # prepare a Task
    due = datetime(2025, 1, 1)
    task = Task("t", "d", due, "brain", "high", "p1")
    brain.network.add_task(task)
    result = brain.list_tasks()
    assert "1. t (Due: 2025-01-01, Priority: high)" in result

def test_detect_send_email_intent_full(monkeypatch, brain):
    # Simulate the LLM returning a fully-specified email intent
    fake_payload = {
        "is_send_email": True,
        "recipient": "alice@example.com",
        "subject": "Hello",
        "body": "Just checking in",
        # note: this will be overridden by the function’s own missing_info logic
        "missing_info": []
    }
    fake_json = json.dumps(fake_payload)

    class FakeChoice:
        def __init__(self, content):
            self.message = type("M", (), {"content": content})

    fake_response = type("R", (), {"choices": [FakeChoice(fake_json)]})

    # Patch brain.client.chat.completions.create to return our fake_response
    monkeypatch.setattr(brain.client.chat.completions, "create", lambda *args, **kwargs: fake_response)

    msg = "send email to alice@example.com subject: Hello body: Just checking in"
    res = brain._detect_send_email_intent(msg)

    assert res["is_send_email"] is True
    assert res["recipient"] == "alice@example.com"
    assert res["subject"]   == "Hello"
    assert res["body"]      == "Just checking in"
    # All fields were provided, so no missing info
    assert res["missing_info"] == []