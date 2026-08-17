from unittest.mock import MagicMock

from hdfc_sky.auth import AuthClient
from hdfc_sky.config import Settings

ENDPOINTS = {
    "auth": {
        "step_1_generate_auth_code": {"method": "GET", "path": "/oapi/v1/login"},
        "step_2_submit_credentials": {"method": "POST", "path": "/oapi/v1/login/credentials"},
        "step_3_request_otp": {"method": "POST", "path": "/oapi/v1/login/otp/generate"},
        "step_4_verify_otp": {"method": "POST", "path": "/oapi/v1/login/otp/verify"},
        "step_5_generate_session_token": {"method": "POST", "path": "/oapi/v1/session/token"},
        "step_6_invalidate_session": {"method": "DELETE", "path": "/oapi/v1/session/token"},
    }
}


def make_settings() -> Settings:
    return Settings(
        api_key="k", api_secret="s", client_id="c", password="p", totp_secret="",
        base_url="https://api.hdfcsky.com", request_timeout_seconds=10,
        session_file="/tmp/does-not-exist-session.json", dry_run=True, endpoints=ENDPOINTS,
    )


def test_login_runs_all_six_steps_and_stores_token():
    http = MagicMock()
    http.request.side_effect = [
        {},  # step 1
        {},  # step 2
        {},  # step 3
        {"request_token": "REQ1"},  # step 4
        {"data": {"access_token": "ACCESS1", "refresh_token": "REFRESH1"}},  # step 5
    ]
    settings = make_settings()
    session_store = MagicMock()
    session_store.load.return_value = None

    auth = AuthClient(http, settings, session_store=session_store)
    token = auth.login(otp_provider=lambda: "123456")

    assert token == "ACCESS1"
    assert http.request.call_count == 5
    http.set_access_token.assert_called_with("ACCESS1")
    session_store.save.assert_called_once_with(
        {"access_token": "ACCESS1", "refresh_token": "REFRESH1"}
    )


def test_login_reuses_cached_session_without_calling_api():
    http = MagicMock()
    settings = make_settings()
    session_store = MagicMock()
    session_store.load.return_value = {"access_token": "CACHED", "refresh_token": "R"}

    auth = AuthClient(http, settings, session_store=session_store)
    token = auth.login()

    assert token == "CACHED"
    http.request.assert_not_called()


def test_logout_calls_step_six_and_clears_local_state():
    http = MagicMock()
    http.request.return_value = {}
    settings = make_settings()
    session_store = MagicMock()

    auth = AuthClient(http, settings, session_store=session_store)
    auth.access_token = "ACCESS1"

    auth.logout()

    http.request.assert_called_once_with("DELETE", "/oapi/v1/session/token")
    assert auth.access_token is None
    session_store.clear.assert_called_once()
