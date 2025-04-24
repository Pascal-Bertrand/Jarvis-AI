import pytest
from datetime import datetime
from network.internal_communication import Intercom
from network.tasks import Task

class DummyNode:
    def __init__(self, node_id):
        self.node_id = node_id
        self.messages = []    # will record (content, sender_id)

    def receive_message(self, content, sender_id):
        self.messages.append((content, sender_id))


def test_intercom_initialization():
    net = Intercom()
    assert isinstance(net, Intercom)
    assert net.nodes == {}
    assert net.tasks == []


def test_register_and_send_message_to_registered_node():
    net = Intercom()
    dummy = DummyNode("n1")
    # register
    net.register_node("n1", dummy)

    # send a message
    net.send_message("alice", "n1", "hello world")

    # DummyNode.receive_message must have been called exactly once
    assert dummy.messages == [("hello world", "alice")]


def test_send_message_to_unknown_node(capfd):
    net = Intercom()

    # no nodes registered yet
    net.send_message("alice", "nope", "are you there?")

    # should print a warning
    out = capfd.readouterr().out
    assert "[Intercom] Unknown recipient: nope." in out


def test_add_task_and_get_tasks_for_node():
    net = Intercom()
    dummy = DummyNode("joe")
    net.register_node("joe", dummy)

    # create a Task from network.tasks (not main.Task)
    due = datetime(2025, 5, 1)
    task = Task(
        title="Write tests",
        description="Cover Intercom methods with pytest",
        due_date=due,
        assigned_to="joe",
        priority="high",
        project_id="proj1"
    )

    # add_task should append it to net.tasks
    net.add_task(task)
    assert task in net.tasks

    # and notify the assigned node
    # (the “system” sender should have sent a notification)
    notifications = [msg for msg, sender in dummy.messages]
    assert any("New task assigned: Write tests" in msg for msg in notifications)

    # get_tasks_for_node must return exactly that task
    tasks_for_joe = net.get_tasks_for_node("joe")
    assert tasks_for_joe == [task]
