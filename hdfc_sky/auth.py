from __future__ import annotations

from typing import Callable

import pyotp

from .config import Settings
from .exceptions import AuthenticationError
from .http_client import HttpClient
from .session_store import SessionStore


class AuthClient:
    """Wraps HDFC Sky's 6-call login flow.

    Every call reads its method/path from config/endpoints.yaml under the
    `auth` section (step_1_... through step_6_...) so fixing a wrong path
    never means touching Python code. The exact request/response field
    names below are best-effort placeholders — cross-check them against
    developer.hdfcsky.com and adjust the `_call` payloads if the real API
    differs.
    """

    def __init__(self, http: HttpClient, settings: Settings, session_store: SessionStore | None = None):
        self.http = http
        self.settings = settings
        self.session_store = session_store or SessionStore(settings.session_file)
        self.access_token: str | None = None
        self.refresh_token: str | None = None

    def _step(self, key: str) -> dict:
        return self.settings.endpoints["auth"][key]

    def _call(self, step_key: str, **kwargs) -> dict:
        step = self._step(step_key)
        path = step["path"].format(**kwargs.pop("path_params", {}))
        return self.http.request(step["method"], path, **kwargs)

    # --- the 6 login steps -------------------------------------------------

    def generate_auth_code(self) -> dict:
        """Step 1: kick off the hosted login (returns a login URL / code)."""
        return self._call(
            "step_1_generate_auth_code",
            params={"api_key": self.settings.api_key},
        )

    def submit_credentials(self) -> dict:
        """Step 2: submit client id + password."""
        return self._call(
            "step_2_submit_credentials",
            json={"client_id": self.settings.client_id, "password": self.settings.password},
        )

    def request_otp(self) -> dict:
        """Step 3: trigger the OTP/TOTP challenge."""
        return self._call("step_3_request_otp", json={"client_id": self.settings.client_id})

    def verify_otp(self, otp: str) -> dict:
        """Step 4: verify the OTP/TOTP, typically returns a request_token."""
        return self._call(
            "step_4_verify_otp",
            json={"client_id": self.settings.client_id, "otp": otp},
        )

    def generate_session_token(self, request_token: str) -> dict:
        """Step 5: exchange request_token for an access_token."""
        return self._call(
            "step_5_generate_session_token",
            json={
                "api_key": self.settings.api_key,
                "request_token": request_token,
                # TODO: HDFC Sky likely requires a checksum here, e.g.
                # sha256(api_key + request_token + api_secret) — confirm the
                # exact recipe in the docs and compute it before enabling
                # DRY_RUN=false.
            },
        )

    def invalidate_session(self) -> dict:
        """Step 6: log out / invalidate the current access token."""
        return self._call("step_6_invalidate_session")

    # --- orchestration -------------------------------------------------

    def login(self, otp_provider: Callable[[], str] | None = None) -> str:
        """Runs the full 6-step flow and returns the access token.

        otp_provider: a zero-arg callable returning the OTP/TOTP to submit.
        Defaults to generating a TOTP from HDFC_SKY_TOTP_SECRET if set,
        otherwise prompts on stdin.
        """
        cached = self.session_store.load()
        if cached and cached.get("access_token"):
            self.access_token = cached["access_token"]
            self.refresh_token = cached.get("refresh_token")
            self.http.set_access_token(self.access_token)
            return self.access_token

        self.generate_auth_code()
        self.submit_credentials()
        self.request_otp()

        otp = otp_provider() if otp_provider else self._default_otp()
        verify_result = self.verify_otp(otp)
        request_token = verify_result.get("request_token") or verify_result.get("data", {}).get("request_token")
        if not request_token:
            raise AuthenticationError(f"No request_token in verify_otp response: {verify_result}")

        session_result = self.generate_session_token(request_token)
        data = session_result.get("data", session_result)
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token:
            raise AuthenticationError(f"No access_token in session response: {session_result}")

        self.access_token = access_token
        self.refresh_token = refresh_token
        self.http.set_access_token(access_token)
        self.session_store.save({"access_token": access_token, "refresh_token": refresh_token})
        return access_token

    def logout(self) -> None:
        try:
            self.invalidate_session()
        finally:
            self.access_token = None
            self.http.set_access_token(None)
            self.session_store.clear()

    def _default_otp(self) -> str:
        if self.settings.totp_secret:
            return pyotp.TOTP(self.settings.totp_secret).now()
        return input("Enter HDFC Sky login OTP: ").strip()
