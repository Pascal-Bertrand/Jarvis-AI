# test_scheduler.py
import pytest
from datetime import datetime, timedelta
from secretary.scheduler import Scheduler
from network.internal_communication import Intercom
from network.tasks import Task
from secretary.brain import Brain

class DummyEvents:
    def __init__(self):
        self.insert_calls = []
        self.list_calls = []
        self.updated_events = {}
        self.deleted_events = []
    def insert(self, calendarId, body):
        self.insert_calls.append((calendarId, body))
        return self
    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        # Return self for chaining
        return self
    def update(self, calendarId, eventId, body):
        self.updated_events[eventId] = body
        return self
    def delete(self, calendarId, eventId):
        self.deleted_events.append(eventId)
        return self
    def execute(self):
        # For insert: pretend to return an event with id and htmlLink
        if self.insert_calls:
            return {"id": "evt1", "htmlLink": "http://example.com/evt1"}
        # For list: return a fixed set of upcoming events
        return {"items": [
            {"id": "evt1",
             "summary": "Test Meeting",
             "start": {"dateTime": (datetime.utcnow()+timedelta(hours=2)).isoformat()+"Z"},
             "attendees": [{"email": "alice@example.com"}, {"email": "bob@example.com"}]},
        ]}

class DummyCalService:
    def __init__(self):
        self._events = DummyEvents()
    def events(self):
        return self._events

@pytest.fixture
def network():
    return Intercom()

@pytest.fixture
def scheduler(network: Intercom):
    return Scheduler(node_id="alice", calendar_service=None, network=network)

def test_init_registers_calendar_attr(network: Intercom):
    sched = Scheduler(node_id="bob", calendar_service=None, network=network)
    # Should register itself on the network
    assert "bob" in network.nodes
    # And add a calendar list to that node
    assert hasattr(network.nodes["bob"], "calendar")
    assert isinstance(network.nodes["bob"].calendar, list)

def test_create_calendar_reminder_no_service(capsys: pytest.CaptureFixture[str], scheduler: Scheduler):
    task = Task("T", "D", datetime.now(), "alice", "low", "p")
    # calendar_service is None by default
    scheduler.create_calendar_reminder(task)
    captured = capsys.readouterr()
    assert "Calendar service not available, skipping reminder creation" in captured.out

def test_create_calendar_reminder_with_service(network: Intercom):
    dummy_cal = DummyCalService()
    sched = Scheduler("alice", calendar_service=dummy_cal, network=network)
    t = Task("T1","D1", datetime(2025,1,1,12,0), "alice", "high", "proj")
    sched.create_calendar_reminder(t)
    # Verify insert called once
    assert dummy_cal._events.insert_calls, "Expected insert to be called"
    calId, body = dummy_cal._events.insert_calls[0]
    assert calId == "primary"
    assert body["summary"] == "TASK: T1"
    assert "Priority: high" in body["description"]

def test_fallback_schedule_meeting(network: Intercom, capsys: pytest.CaptureFixture[str]):
    # Pre-register bob so he can be notified
    dummy_bob = type("Node", (), {})()
    dummy_bob.calendar = []
    network.register_node("bob", dummy_bob)

    sched = Scheduler("alice", calendar_service=None, network=network)
    sched._fallback_schedule_meeting("projX", ["alice", "bob"])

    # Both alice and bob should have calendar entries
    assert sched.calendar, "Scheduler calendar should be populated"
    assert any(m["project_id"] == "projX" for m in sched.calendar)
    assert any(m["project_id"] == "projX" for m in network.nodes["bob"].calendar)

    # Our fallback now only logs, so no stdout
    out = capsys.readouterr().out
    assert out == ""


def test_schedule_meeting_with_service(network: Intercom):
    dummy_cal = DummyCalService()
    sched = Scheduler("alice", calendar_service=dummy_cal, network=network)
    # Register participants
    network.register_node("bob", sched)
    network.register_node("charlie", sched)
    # Track send_message calls
    sent = []
    network.send_message = lambda s,r,c: sent.append((s,r,c))
    sched.schedule_meeting("projY", ["alice","bob","charlie"])
    # Should have inserted exactly one event
    assert len(dummy_cal._events.insert_calls) == 1
    # Scheduler calendar updated
    assert any(m["project_id"]=="projY" for m in sched.calendar)
    # Other participants have calendar entries
    assert any(m["project_id"]=="projY" for m in network.nodes["bob"].calendar)
    # Notifications sent to bob and charlie
    assert any(r=="bob" for _,r,_ in sent)
    assert any(r=="charlie" for _,r,_ in sent)

def test_handle_calendar_dispatches(monkeypatch):
    sched = Scheduler("alice", calendar_service=None, network=Intercom(), brain=Brain)
    called = {}

    # Stub out all handler methods with a signature that accepts anything
    for action in [
        "_handle_meeting_creation",
        "_start_meeting_creation",
        "_handle_list_meetings",
        "_handle_meeting_cancellation",
        "_handle_meeting_rescheduling"
    ]:
        monkeypatch.setattr(
            sched,
            action,
            lambda *args, act=action, **kwargs: called.setdefault(act, True)
        )

    # schedule_meeting without missing_info → should call _handle_meeting_creation
    intent = {"is_calendar_command": True, "action": "schedule_meeting", "missing_info": []}
    sched.handle_calendar(intent, "msg")
    assert called.get("_handle_meeting_creation")
    called.clear()

    # schedule_meeting with missing_info → should call _start_meeting_creation
    intent["missing_info"] = ["date"]
    sched.handle_calendar(intent, "msg2")
    assert called.get("_start_meeting_creation")
    called.clear()

    # list_meetings → should call _handle_list_meetings
    intent = {"is_calendar_command": True, "action": "list_meetings", "missing_info": []}
    sched.handle_calendar(intent, "msg3")
    assert called.get("_handle_list_meetings")
    called.clear()

    # cancel_meeting → should call _handle_meeting_cancellation
    intent["action"] = "cancel_meeting"
    sched.handle_calendar(intent, "msg4")
    assert called.get("_handle_meeting_cancellation")
    called.clear()

    # reschedule_meeting → should call _handle_meeting_rescheduling
    intent["action"] = "reschedule_meeting"
    sched.handle_calendar(intent, "msg5")
    assert called.get("_handle_meeting_rescheduling")

def test_handle_list_meetings_outputs(network: Intercom, capsys: pytest.CaptureFixture[str]):
    dummy_cal = DummyCalService()
    sched = Scheduler("alice", calendar_service=dummy_cal, network=network)
    # capture list_meetings output
    sched._handle_list_meetings()
    out = capsys.readouterr().out
    assert "Upcoming meetings:" in out
    assert "Test Meeting" in out

def test_construct_and_continue_meeting_flow(capsys: pytest.CaptureFixture[str]):
    sched = Scheduler("alice", calendar_service=None, network=Intercom())
    # Start with missing two pieces
    sched._start_meeting_creation("Let's meet", ["date","time"])
    # First question printed
    out1 = capsys.readouterr().out
    assert "What date should the meeting be scheduled?" in out1 or "On what date" in out1
    # Simulate replying
    sched._continue_meeting_creation("2025-05-01", "alice")
    # Now should ask for time
    out2 = capsys.readouterr().out
    assert "What time should the meeting be scheduled?" in out2
    # Fill last piece
    sched._continue_meeting_creation("14:00", "alice")
    out3 = capsys.readouterr().out
    assert "scheduled successfully" in out3

def test_complete_meeting_rescheduling_no_context(network: Intercom):
    # Should simply do nothing / not raise
    sched = Scheduler("alice", calendar_service=DummyCalService(), network=network)
    # No meeting_context defined
    sched._complete_meeting_rescheduling()  # no exception

# End of test_scheduler.py
