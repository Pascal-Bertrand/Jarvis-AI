# tests/test_google.py
import os
import pickle
import pytest
from types import SimpleNamespace

from secretary.utilities import google as google_mod

# A dummy “credentials” object
class DummyCreds:
    valid = False
    expired = True
    refresh_token = True
    def refresh(self, req): pass

# A dummy OAuth flow that never actually starts a server
class DummyFlow:
    @staticmethod
    def from_client_config(cfg, scopes):
        return DummyFlow()
    def authorization_url(self, prompt):
        return "http://fake.auth", None
    def run_local_server(self, port):
        return DummyCreds()

# Dummy builds for Calendar/Gmail
def fake_build(service, version, credentials):
    if service == "calendar":
        # minimal object to let us call .calendarList().list().execute()
        return SimpleNamespace(
            calendarList=lambda: SimpleNamespace(list=lambda: SimpleNamespace(execute=lambda: {"items":[]}))
        )
    if service == "gmail":
        return SimpleNamespace(
            users=lambda: SimpleNamespace(getProfile=lambda userId: SimpleNamespace(execute=lambda: {"emailAddress":"me@example.com"}))
        )

@pytest.fixture(autouse=True)
def patch_oauth(monkeypatch, tmp_path):
    # point TOKEN_FILE to a temp file (so no real file)
    monkeypatch.setattr(google_mod, "TOKEN_FILE", str(tmp_path / "token.pickle"))
    # Always say we have a client secret
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake_secret")
    # Patch the OAuth flow and the build calls
    monkeypatch.setattr(google_mod, "InstalledAppFlow", DummyFlow)
    monkeypatch.setattr(google_mod, "build", fake_build)
    # Pretend no token file exists initially
    monkeypatch.setattr(google_mod.os.path, "exists", lambda p: False)

def test_initialize_google_services(monkeypatch):
    services = google_mod.initialize_google_services("unit_test")
    assert services["calendar"] is not None
    assert services["gmail"] is not None
