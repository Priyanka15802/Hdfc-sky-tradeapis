"""Thin wrapper around every HDFC Sky Open API call this tool uses.

Every function here mirrors one curl from HDFC's own API doc as closely as
possible: same host, same path, same method, same query params, same body
shape. Nothing here is guessed — where the doc didn't specify something
(most notably Modify GTT Orders, which has no documented body), there is
no function for it; app.py surfaces that as a disabled action instead of
inventing a payload.

Response shapes were never shown in the doc either, so `request()` returns
the raw parsed JSON untouched. app.py is responsible for pulling whatever
fields it needs (token_id, request_token, access_token, ...) out of that,
and for showing the raw response to the user so they can see exactly what
HDFC sent back.
"""
from __future__ import annotations

import requests

PROD_BASE = "https://developer.hdfcsky.com"
UAT_BASE = "https://uat-developer.hdfcsky.com"

# Every curl in HDFC's doc includes this exact User-Agent header.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


class HdfcApiError(Exception):
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"HDFC Sky API error {status_code}: {payload}")


def _request(method: str, url: str, headers: dict, timeout: float, **kwargs) -> dict:
    headers = {"User-Agent": USER_AGENT, **headers}
    response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {"raw": response.text}
    if not response.ok:
        raise HdfcApiError(response.status_code, payload)
    return payload


# --- Login (7 calls) -------------------------------------------------

def get_token_id(api_key: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/login?api_key={api_key}"
    return _request("GET", url, {}, timeout)


def validate_username(api_key: str, token_id: str, username: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/login-channel/validate?api_key={api_key}&token_id={token_id}"
    return _request("POST", url, {"Content-Type": "application/json"}, timeout,
                     json={"username": username})


def validate_otp(api_key: str, token_id: str, otp: str, timeout: float) -> dict:
    # HDFC's doc shows this one login step on the UAT host while every
    # other login step (including the token_id this call depends on) is on
    # prod — that produced a real 401 "invalid login attempt" in testing,
    # consistent with the UAT environment never having seen a prod
    # token_id. Using prod here instead, matching the rest of the flow.
    url = f"{PROD_BASE}/oapi/v1/otp/validate?api_key={api_key}&token_id={token_id}"
    return _request("PUT", url, {"Content-Type": "application/json"}, timeout,
                     json={"otp": otp})


def resend_otp(api_key: str, token_id: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/twofa/resend?api_key={api_key}&token_id={token_id}"
    return _request("GET", url, {}, timeout)


def validate_pin(api_key: str, token_id: str, answer: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/twofa/validate?api_key={api_key}&token_id={token_id}"
    return _request("POST", url, {"Content-Type": "application/json"}, timeout,
                     json={"answer": answer})


def authorise(api_key: str, token_id: str, consent: str, request_token: str, timeout: float) -> dict:
    url = (f"{PROD_BASE}/oapi/v1/authorise?api_key={api_key}&token_id={token_id}"
           f"&consent={consent}&request_token={request_token}")
    return _request("GET", url, {"Content-Type": "application/json"}, timeout)


def get_access_token(api_key: str, request_token: str, api_secret: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/access-token?api_key={api_key}&request_token={request_token}"
    return _request("POST", url, {"Content-Type": "application/json"}, timeout,
                     json={"apiSecret": api_secret})


# --- Orders: shared auth header -------------------------------------

def _auth_headers(access_token: str) -> dict:
    return {"Authorization": access_token, "Content-Type": "application/json"}


# --- Regular orders ---------------------------------------------------

def place_regular_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders?api_key={api_key}"
    return _request("POST", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "REGULAR"})


def modify_regular_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders?api_key={api_key}"
    return _request("PUT", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "REGULAR"})


def cancel_regular_order(api_key: str, access_token: str, oms_order_id: str,
                          client_id: str, timeout: float) -> dict:
    url = (f"{PROD_BASE}/oapi/v1/orders/{oms_order_id}?api_key={api_key}"
           f"&client_id={client_id}&execution_type=REGULAR")
    return _request("DELETE", url, _auth_headers(access_token), timeout)


# --- AMO orders ---------------------------------------------------

def place_amo_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders?api_key={api_key}"
    return _request("POST", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "AMO"})


def modify_amo_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders?api_key={api_key}"
    return _request("PUT", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "AMO"})


def cancel_amo_order(api_key: str, access_token: str, oms_order_id: str,
                      client_id: str, timeout: float) -> dict:
    url = (f"{PROD_BASE}/oapi/v1/orders/kart/{oms_order_id}?api_key={api_key}"
           f"&client_id={client_id}&execution_type=AMO")
    return _request("DELETE", url, _auth_headers(access_token), timeout)


# --- Cover orders ---------------------------------------------------

def place_cover_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders/kart?api_key={api_key}"
    return _request("POST", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "CO"})


def modify_cover_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders/kart?api_key={api_key}"
    return _request("PUT", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "CO"})


def cancel_cover_order(api_key: str, access_token: str, oms_order_id: str,
                        body: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders/kart/{oms_order_id}?api_key={api_key}"
    return _request("DELETE", url, _auth_headers(access_token), timeout,
                     json={**body, "execution_type": "CO"})


# --- Bracket orders ---------------------------------------------------

def place_bracket_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders/kart?api_key={api_key}"
    return _request("POST", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "BO"})


def modify_bracket_order(api_key: str, access_token: str, order: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders/kart?api_key={api_key}"
    return _request("PUT", url, _auth_headers(access_token), timeout,
                     json={**order, "execution_type": "BO"})


def exit_bracket_order(api_key: str, access_token: str, oms_order_id: str,
                        body: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/orders/kart/{oms_order_id}?api_key={api_key}"
    return _request("DELETE", url, _auth_headers(access_token), timeout,
                     json={**body, "execution_type": "BO"})


# --- GTT orders ---------------------------------------------------
# NOTE: Modify GTT Orders is intentionally absent. HDFC's doc gives no
# request body or way to identify which GTT to modify for that endpoint
# (PUT /oapi/v1/event/gtt) — nothing to build against yet.
#
# Doc shows these on the UAT host, but (like LTP and OTP) the access_token
# is prod-issued, so they use prod here too.

def place_gtt_order(api_key: str, access_token: str, gtt: dict, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/event/gtt?api_key={api_key}"
    return _request("POST", url, _auth_headers(access_token), timeout, json=gtt)


def cancel_gtt_order(api_key: str, access_token: str, client_id: str, gtt_id: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/event/gtt/{client_id}/{gtt_id}?api_key={api_key}"
    return _request("DELETE", url, _auth_headers(access_token), timeout)


def fetch_gtt_orders(api_key: str, access_token: str, client_id: str, timeout: float) -> dict:
    url = f"{PROD_BASE}/oapi/v1/event/gtt/{client_id}?api_key={api_key}"
    return _request("GET", url, {"Authorization": access_token}, timeout)


# --- LTP ---------------------------------------------------

def fetch_ltp(api_key: str, access_token: str, watchlist: list, timeout: float) -> dict:
    # HDFC's doc shows this on the UAT host, but the access_token is issued
    # by prod — authenticating it against UAT fails (same root cause as the
    # OTP-validate host fix). Using prod so the prod-issued token is valid.
    url = f"{PROD_BASE}/oapi/v1/fetch-ltp?api_key={api_key}"
    return _request("PUT", url, _auth_headers(access_token), timeout,
                     json={"data": watchlist})
