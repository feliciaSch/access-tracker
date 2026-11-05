def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "ok"
    assert "X-Request-ID" in r.headers


def test_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-me-123"})
    assert r.headers["X-Request-ID"] == "trace-me-123"


def test_requests_need_login(client):
    assert client.get("/requests").status_code == 401


def test_wrong_password_rejected(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "not-the-password"})
    assert r.status_code == 401


def test_duplicate_username_rejected(client, user_headers):
    r = client.post("/auth/register", json={"username": "alice", "password": "another-pass-1"})
    assert r.status_code == 409


def test_full_lifecycle(client, user_headers, admin_headers):
    # alice submits a request
    r = client.post("/requests", headers=user_headers, json={
        "resource": "prod-postgres", "access_level": "read", "justification": "Investigating ticket OPS-42"})
    assert r.status_code == 201
    req = r.json()
    assert req["status"] == "pending" and req["requester"] == "alice"

    # it shows up when filtering by pending
    r = client.get("/requests?status=pending", headers=user_headers)
    assert any(x["id"] == req["id"] for x in r.json())

    # alice is not an approver, so she can't approve her own request
    r = client.patch(f"/requests/{req['id']}/status", headers=user_headers, json={"status": "approved"})
    assert r.status_code == 403

    # admin approves it
    r = client.patch(f"/requests/{req['id']}/status", headers=admin_headers,
                     json={"status": "approved", "note": "ok for 7 days"})
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # filters reflect the new status
    r = client.get("/requests?status=pending", headers=user_headers)
    assert all(x["id"] != req["id"] for x in r.json())

    # audit trail has both events, in order
    r = client.get(f"/requests/{req['id']}/audit", headers=user_headers)
    events = r.json()
    assert [e["action"] for e in events] == ["created", "status_changed"]
    assert events[1]["old_status"] == "pending" and events[1]["new_status"] == "approved"
    assert events[1]["actor"] == "admin"


def test_invalid_input_rejected(client, user_headers):
    r = client.post("/requests", headers=user_headers, json={
        "resource": "x", "access_level": "superuser", "justification": "because"})
    assert r.status_code == 422


def test_unknown_request_404(client, user_headers):
    assert client.get("/requests/99999", headers=user_headers).status_code == 404


def test_debug_error_returns_500_with_request_id(client):
    r = client.get("/debug/error")
    assert r.status_code == 500
    assert r.json()["request_id"] == r.headers["X-Request-ID"]
