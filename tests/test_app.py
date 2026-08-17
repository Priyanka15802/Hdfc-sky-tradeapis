import importlib
from unittest.mock import patch

import pytest


def _make_app(monkeypatch, dry_run="true"):
    monkeypatch.setenv("HDFC_SKY_API_KEY", "KEY")
    monkeypatch.setenv("HDFC_SKY_API_SECRET", "SECRET")
    monkeypatch.setenv("HDFC_SKY_CLIENT_ID", "DEFAULTCID")
    monkeypatch.setenv("HDFC_SKY_CONSENT", "true")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DRY_RUN", dry_run)
    import app as app_module
    importlib.reload(app_module)
    app_module.app.config.update(TESTING=True)
    return app_module


def _login(client):
    """Drives the 3 user-facing steps (Client ID, OTP, MPIN); Get Token ID
    and Authorise happen server-side inside begin/finish."""
    with patch("hdfc_client.get_token_id", return_value={"token_id": "TOK"}), \
         patch("hdfc_client.validate_username", return_value={}), \
         patch("hdfc_client.validate_otp", return_value={}), \
         patch("hdfc_client.validate_pin", return_value={"request_token": "REQ"}), \
         patch("hdfc_client.authorise", return_value={}), \
         patch("hdfc_client.get_access_token", return_value={"access_token": "AT", "client_id": "CID"}):
        client.post("/api/login/begin", json={"username": "u"})
        client.post("/api/login/otp", json={"otp": "1234"})
        client.post("/api/login/finish", json={"answer": "1234"})


def test_status_when_not_logged_in(monkeypatch):
    app_module = _make_app(monkeypatch)
    client = app_module.app.test_client()
    r = client.get("/api/status")
    assert r.get_json()["logged_in"] is False


def test_full_login_flow_sets_session(monkeypatch):
    app_module = _make_app(monkeypatch)
    client = app_module.app.test_client()
    _login(client)
    r = client.get("/api/status")
    body = r.get_json()
    assert body["logged_in"] is True
    assert body["client_id"] == "CID"


def test_login_begin_chains_get_token_id_and_validate_username(monkeypatch):
    app_module = _make_app(monkeypatch)
    client = app_module.app.test_client()
    with patch("hdfc_client.get_token_id", return_value={"token_id": "TOK"}) as mock_token, \
         patch("hdfc_client.validate_username", return_value={"ok": True}) as mock_user:
        r = client.post("/api/login/begin", json={"username": "u"})
        assert r.get_json()["ok"] is True
        mock_token.assert_called_once()
        mock_user.assert_called_once_with("KEY", "TOK", "u", app_module.TIMEOUT)


def test_login_finish_uses_consent_from_env_not_user_input(monkeypatch):
    app_module = _make_app(monkeypatch)
    client = app_module.app.test_client()
    with patch("hdfc_client.get_token_id", return_value={"token_id": "TOK"}), \
         patch("hdfc_client.validate_username", return_value={}):
        client.post("/api/login/begin", json={"username": "u"})
    with patch("hdfc_client.validate_pin", return_value={"request_token": "REQ"}), \
         patch("hdfc_client.authorise", return_value={}) as mock_auth, \
         patch("hdfc_client.get_access_token", return_value={"access_token": "AT", "client_id": "CID"}):
        r = client.post("/api/login/finish", json={"answer": "1234"})
        assert r.get_json()["logged_in"] is True
        mock_auth.assert_called_once_with("KEY", "TOK", "true", "REQ", app_module.TIMEOUT)


def test_login_finish_fails_without_consent_env(monkeypatch):
    app_module = _make_app(monkeypatch)
    monkeypatch.delenv("HDFC_SKY_CONSENT", raising=False)
    importlib.reload(app_module)
    client = app_module.app.test_client()
    with patch("hdfc_client.get_token_id", return_value={"token_id": "TOK"}), \
         patch("hdfc_client.validate_username", return_value={}):
        client.post("/api/login/begin", json={"username": "u"})
    r = client.post("/api/login/finish", json={"answer": "1234"})
    assert r.status_code == 400
    assert "HDFC_SKY_CONSENT" in r.get_json()["error"]


def test_dry_run_toggle_endpoint(monkeypatch):
    app_module = _make_app(monkeypatch, dry_run="true")
    client = app_module.app.test_client()
    assert client.get("/api/status").get_json()["dry_run"] is True

    r = client.post("/api/dry-run", json={"enabled": False})
    assert r.get_json()["dry_run"] is False
    assert client.get("/api/status").get_json()["dry_run"] is False


def test_dry_run_toggle_is_per_session_not_global(monkeypatch):
    app_module = _make_app(monkeypatch, dry_run="true")
    client_a = app_module.app.test_client()
    client_b = app_module.app.test_client()
    client_a.post("/api/dry-run", json={"enabled": False})
    assert client_a.get("/api/status").get_json()["dry_run"] is False
    assert client_b.get("/api/status").get_json()["dry_run"] is True


def test_order_route_requires_login(monkeypatch):
    app_module = _make_app(monkeypatch)
    client = app_module.app.test_client()
    r = client.post("/api/orders/regular", json={"exchange": "NSE"})
    assert r.status_code == 401


def test_place_regular_order_dry_run_does_not_call_hdfc(monkeypatch):
    app_module = _make_app(monkeypatch, dry_run="true")
    client = app_module.app.test_client()
    _login(client)
    with patch("hdfc_client.place_regular_order") as mock_place:
        r = client.post("/api/orders/regular", json={"exchange": "NSE", "quantity": 1})
        body = r.get_json()
        assert body["dry_run"] is True
        assert body["would_send"]["body"]["execution_type"] == "REGULAR"
        mock_place.assert_not_called()


def test_place_regular_order_live_calls_hdfc(monkeypatch):
    app_module = _make_app(monkeypatch, dry_run="false")
    client = app_module.app.test_client()
    _login(client)
    with patch("hdfc_client.place_regular_order", return_value={"oms_order_id": "1"}) as mock_place:
        r = client.post("/api/orders/regular", json={"exchange": "NSE", "quantity": 1})
        assert r.get_json()["raw"]["oms_order_id"] == "1"
        mock_place.assert_called_once()


def test_cancel_gtt_is_dry_run_gated(monkeypatch):
    app_module = _make_app(monkeypatch, dry_run="true")
    client = app_module.app.test_client()
    _login(client)
    with patch("hdfc_client.cancel_gtt_order") as mock_cancel:
        r = client.delete("/api/orders/gtt/CID/G1")
        assert r.get_json()["dry_run"] is True
        mock_cancel.assert_not_called()


def test_fetch_gtt_is_not_dry_run_gated(monkeypatch):
    app_module = _make_app(monkeypatch, dry_run="true")
    client = app_module.app.test_client()
    _login(client)
    with patch("hdfc_client.fetch_gtt_orders", return_value={"orders": []}) as mock_fetch:
        r = client.get("/api/orders/gtt/CID")
        assert r.get_json()["raw"] == {"orders": []}
        mock_fetch.assert_called_once()
