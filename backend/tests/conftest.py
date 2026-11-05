import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file BEFORE it is imported.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin-password-123"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _token(client, username, password, register=False):
    path = "/auth/register" if register else "/auth/login"
    r = client.post(path, json={"username": username, "password": password})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    return _token(client, "admin", "admin-password-123")


@pytest.fixture(scope="session")
def user_headers(client):
    return _token(client, "alice", "alice-password-1", register=True)
