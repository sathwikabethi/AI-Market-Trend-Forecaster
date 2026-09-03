import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.mfa import totp_code


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def _register_and_get_token(client: TestClient) -> str:
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "name": "Test User",
        "email": email,
        "password": "StrongPass123",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 200
    return response.json()["access_token"]


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/auth/login",
        json={"email": "admin@caresense.local", "password": "Admin@123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_endpoints(client: TestClient):
    liveness = client.get("/health/liveness")
    assert liveness.status_code == 200
    assert liveness.json()["status"] == "alive"

    readiness = client.get("/health/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"


def test_auth_register_login_and_me(client: TestClient):
    email = f"auth-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123"
    register = client.post(
        "/auth/register",
        json={"name": "Auth User", "email": email, "password": password},
    )
    assert register.status_code == 200
    token = register.json()["access_token"]
    assert register.json().get("refresh_token")
    assert token

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    login_token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {login_token}"})
    assert logout.status_code == 200
    assert logout.json()["status"] == "logged_out"

    me_after_logout = client.get("/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    assert me_after_logout.status_code == 401


def test_data_status_products_and_trends(client: TestClient):
    status = client.get("/data/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["raw_rows"] >= 0
    assert payload["processed_rows"] >= 0

    products = client.get("/products")
    assert products.status_code == 200
    items = products.json()
    assert isinstance(items, list)
    assert len(items) > 0

    trends = client.get("/trends", params={"product": items[0]["id"]})
    assert trends.status_code == 200
    trend_payload = trends.json()
    assert isinstance(trend_payload["trends"], list)


def test_analyze_endpoint_returns_kpis_and_alerts(client: TestClient):
    payload = {
        "text": "Excellent texture and lightweight feel, but price is a little high.",
        "product": "sunscreen",
    }
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "aspects" in data
    assert "business_kpis" in data
    assert "customer_satisfaction_index" in data["business_kpis"]
    assert isinstance(data["alerts"], list)


def test_preprocessing_audits_endpoint(client: TestClient):
    response = client.get("/data/preprocessing-audits")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) > 0
    assert "run_id" in payload[0]
    assert "avg_clean_token_count" in payload[0]


def test_admin_overview_requires_admin_role(client: TestClient):
    user_token = _register_and_get_token(client)
    user_response = client.get(
        "/admin/overview",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert user_response.status_code == 403

    admin_token = _admin_token(client)
    admin_response = client.get(
        "/admin/overview",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_response.status_code == 200
    data = admin_response.json()
    assert "data_status" in data
    assert "preprocessing_audits" in data
    assert "ingestion_runs" in data
    assert "queue" in data


def test_manual_ingestion_endpoint(client: TestClient):
    admin_token = _admin_token(client)
    trigger = client.post(
        "/ingestion/run",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"source": "test-suite", "batch_size": 2},
    )
    assert trigger.status_code == 200
    assert trigger.json()["status"] == "queued"

    runs = client.get(
        "/ingestion/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert runs.status_code == 200
    assert isinstance(runs.json(), list)

    queue_status = client.get(
        "/queue/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert queue_status.status_code == 200
    assert "redis_enabled" in queue_status.json()


def test_auth_refresh_rotates_and_detects_reuse(client: TestClient):
    email = f"refresh-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123"
    register = client.post(
        "/auth/register",
        json={"name": "Refresh User", "email": email, "password": password},
    )
    assert register.status_code == 200
    access_token = register.json()["access_token"]
    refresh_token = register.json()["refresh_token"]

    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    new_access_token = refreshed.json()["access_token"]
    new_refresh_token = refreshed.json()["refresh_token"]
    assert new_access_token != access_token
    assert new_refresh_token != refresh_token

    # Old access token should be invalid after refresh (session jti rotated).
    me_old = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_old.status_code == 401

    me_new = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_new.status_code == 200

    # Reusing an already-used refresh token should be rejected and revoke the family.
    reuse = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse.status_code == 401


def test_job_idempotency_key_dedupes(client: TestClient):
    token = _register_and_get_token(client)
    idempotency_key = f"idemp-{uuid.uuid4().hex}"
    payload = {
        "text": "Great sunscreen texture but a bit pricey.",
        "product": "sunscreen",
        "idempotency_key": idempotency_key,
    }
    first = client.post("/jobs/analyze", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert first.status_code == 200
    job_id_1 = first.json()["job_id"]

    second = client.post("/jobs/analyze", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert second.status_code == 200
    job_id_2 = second.json()["job_id"]

    assert job_id_1 == job_id_2

    status = client.get(f"/jobs/{job_id_1}", headers={"Authorization": f"Bearer {token}"})
    assert status.status_code == 200
    body = status.json()
    assert body["job_id"] == job_id_1
    assert body.get("idempotency_key") == idempotency_key


def test_data_quality_endpoints_admin_only(client: TestClient):
    user_token = _register_and_get_token(client)
    user_run = client.post(
        "/data/quality/run",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert user_run.status_code == 403

    admin_token = _admin_token(client)
    run = client.post(
        "/data/quality/run",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert run.status_code == 200
    payload = run.json()
    assert "run_id" in payload
    assert "score" in payload

    runs = client.get(
        "/data/quality/runs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert runs.status_code == 200
    assert isinstance(runs.json(), list)


def test_rag_endpoints(client: TestClient):
    token = _register_and_get_token(client)
    status = client.get("/rag/status")
    assert status.status_code == 200
    assert "documents_indexed" in status.json()

    ask = client.post(
        "/rag/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What do users say about sunscreen texture?", "product": "sunscreen", "top_k": 4},
    )
    assert ask.status_code == 200
    payload = ask.json()
    assert "answer" in payload
    assert isinstance(payload.get("retrieved"), list)


def test_api_prefix_and_version_aliases(client: TestClient):
    for prefix in ("/api", "/api/v1", "/v1"):
        response = client.get(f"{prefix}/health/liveness")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


def test_mfa_setup_enable_and_login_requires_code(client: TestClient):
    email = f"mfa-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123"
    register = client.post(
        "/auth/register",
        json={"name": "MFA User", "email": email, "password": password},
    )
    assert register.status_code == 200
    access_token = register.json()["access_token"]

    setup = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert setup.status_code == 200
    setup_payload = setup.json()
    assert setup_payload.get("secret_base32")
    assert isinstance(setup_payload.get("backup_codes"), list)
    assert len(setup_payload["backup_codes"]) > 0

    code = totp_code(setup_payload["secret_base32"])
    enable = client.post(
        "/auth/mfa/enable",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": code},
    )
    assert enable.status_code == 200
    assert enable.json().get("status") in {"enabled", "already_enabled"}

    login_without_code = client.post("/auth/login", json={"email": email, "password": password})
    assert login_without_code.status_code == 401
    assert "mfa" in str(login_without_code.json().get("detail", "")).lower()

    login_with_totp = client.post("/auth/login", json={"email": email, "password": password, "mfa_code": code})
    assert login_with_totp.status_code == 200

    backup_code = setup_payload["backup_codes"][0]
    login_with_backup = client.post(
        "/auth/login",
        json={"email": email, "password": password, "mfa_code": backup_code},
    )
    assert login_with_backup.status_code == 200

    backup_reuse = client.post(
        "/auth/login",
        json={"email": email, "password": password, "mfa_code": backup_code},
    )
    assert backup_reuse.status_code == 401


def test_email_verification_request_and_confirm(client: TestClient):
    email = f"verify-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123"
    register = client.post(
        "/auth/register",
        json={"name": "Verify User", "email": email, "password": password},
    )
    assert register.status_code == 200

    request_token = client.post("/auth/email/verification/request", json={"email": email})
    assert request_token.status_code == 200
    token_payload = request_token.json()
    assert token_payload.get("status") in {"sent", "already_verified"}
    token_value = token_payload.get("token")
    assert token_value  # returned in non-production by design

    confirm = client.post("/auth/email/verification/confirm", json={"token": token_value})
    assert confirm.status_code == 200
    assert confirm.json().get("status") in {"verified", "already_verified"}

    request_again = client.post("/auth/email/verification/request", json={"email": email})
    assert request_again.status_code == 200
    assert request_again.json().get("status") == "already_verified"


def test_password_reset_revokes_sessions_and_allows_new_login(client: TestClient):
    email = f"reset-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPass123"
    register = client.post(
        "/auth/register",
        json={"name": "Reset User", "email": email, "password": password},
    )
    assert register.status_code == 200
    access_token = register.json()["access_token"]
    refresh_token = register.json()["refresh_token"]

    req = client.post("/auth/password/reset/request", json={"email": email})
    assert req.status_code == 200
    token_value = req.json().get("token")
    assert token_value

    new_password = "NewStrongPass123"
    confirm = client.post(
        "/auth/password/reset/confirm",
        json={"token": token_value, "new_password": new_password},
    )
    assert confirm.status_code == 200
    assert confirm.json().get("status") == "reset"

    # Existing sessions should be revoked.
    me_old = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_old.status_code == 401

    refresh_old = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_old.status_code == 401

    login_old = client.post("/auth/login", json={"email": email, "password": password})
    assert login_old.status_code == 401

    login_new = client.post("/auth/login", json={"email": email, "password": new_password})
    assert login_new.status_code == 200
