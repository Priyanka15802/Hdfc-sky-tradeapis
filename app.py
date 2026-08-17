"""Flask backend for the HDFC Sky lite trading tool.

Keeps api_key/api_secret server-side (from .env) and the per-login
token_id/request_token/access_token in the server-side session — none of
that ever reaches browser JS directly except access_token's presence
(true/false), so the frontend can tell if it's logged in.

HDFC's docs never show response bodies, so this file doesn't assume a
fixed shape for them: `_extract` tries a handful of common key spellings
and otherwise leaves the field blank for the user to fill in by hand after
looking at the raw response (echoed back in every /api/login/* reply as
"raw").

Order-mutating calls (place/modify/cancel, everywhere) are gated by
DRY_RUN (default true): with it on, the exact request that *would* be
sent is returned instead of actually sending it, so you can verify
payloads against your real account behaviour before risking a live order.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session

import hdfc_client
from hdfc_client import HdfcApiError

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

API_KEY = os.environ.get("HDFC_SKY_API_KEY", "")
API_SECRET = os.environ.get("HDFC_SKY_API_SECRET", "")
DEFAULT_CLIENT_ID = os.environ.get("HDFC_SKY_CLIENT_ID", "")
TIMEOUT = float(os.environ.get("HDFC_SKY_REQUEST_TIMEOUT_SECONDS", "10"))
DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() in ("1", "true", "yes")


def _extract(payload, *candidates):
    """Best-effort pull of a field out of an HDFC response of unknown shape.

    Tries each candidate key at the top level and inside a nested "data"
    object. Returns None (never guesses a value) if nothing matches.
    """
    if not isinstance(payload, dict):
        return None
    for key in candidates:
        if key in payload:
            return payload[key]
    nested = payload.get("data")
    if isinstance(nested, dict):
        for key in candidates:
            if key in nested:
                return nested[key]
    return None


def _require_login():
    if not session.get("access_token"):
        return jsonify(error="Not logged in. Complete the login flow first."), 401
    return None


def _mutate(description: dict, fn, *args):
    """Runs an order-mutating HDFC call, or short-circuits under DRY_RUN."""
    if DRY_RUN:
        return jsonify(dry_run=True, would_send=description)
    return jsonify(raw=fn(*args))


@app.errorhandler(HdfcApiError)
def handle_hdfc_error(err: HdfcApiError):
    return jsonify(error="HDFC Sky API error", status_code=err.status_code, payload=err.payload), 502


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/status")
def status():
    return jsonify(
        logged_in=bool(session.get("access_token")),
        client_id=session.get("client_id") or DEFAULT_CLIENT_ID,
        api_key_configured=bool(API_KEY),
        dry_run=DRY_RUN,
    )


# --- Login flow -------------------------------------------------

@app.post("/api/login/start")
def login_start():
    if not API_KEY:
        return jsonify(error="HDFC_SKY_API_KEY is not set in .env"), 400
    raw = hdfc_client.get_token_id(API_KEY, TIMEOUT)
    token_id = _extract(raw, "token_id", "tokenId")
    if token_id:
        session["token_id"] = token_id
    return jsonify(raw=raw, token_id=token_id)


@app.post("/api/login/username")
def login_username():
    body = request.get_json(force=True)
    token_id = session.get("token_id") or body.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — call /api/login/start first"), 400
    session["token_id"] = token_id
    raw = hdfc_client.validate_username(API_KEY, token_id, body["username"], TIMEOUT)
    return jsonify(raw=raw)


@app.post("/api/login/otp")
def login_otp():
    body = request.get_json(force=True)
    token_id = session.get("token_id") or body.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — call /api/login/start first"), 400
    raw = hdfc_client.validate_otp(API_KEY, token_id, body["otp"], TIMEOUT)
    request_token = _extract(raw, "request_token", "requestToken")
    if request_token:
        session["request_token"] = request_token
    return jsonify(raw=raw, request_token=request_token)


@app.post("/api/login/otp/resend")
def login_otp_resend():
    token_id = session.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — call /api/login/start first"), 400
    raw = hdfc_client.resend_otp(API_KEY, token_id, TIMEOUT)
    return jsonify(raw=raw)


@app.post("/api/login/pin")
def login_pin():
    body = request.get_json(force=True)
    token_id = session.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — call /api/login/start first"), 400
    raw = hdfc_client.validate_pin(API_KEY, token_id, body["answer"], TIMEOUT)
    request_token = _extract(raw, "request_token", "requestToken")
    if request_token:
        session["request_token"] = request_token
    return jsonify(raw=raw, request_token=request_token)


@app.post("/api/login/authorise")
def login_authorise():
    body = request.get_json(force=True)
    token_id = session.get("token_id")
    request_token = body.get("request_token") or session.get("request_token")
    consent = body["consent"]
    if not token_id or not request_token:
        return jsonify(error="Missing token_id or request_token — complete earlier login steps first"), 400
    raw = hdfc_client.authorise(API_KEY, token_id, consent, request_token, TIMEOUT)
    new_request_token = _extract(raw, "request_token", "requestToken") or request_token
    session["request_token"] = new_request_token
    return jsonify(raw=raw, request_token=new_request_token)


@app.post("/api/login/access-token")
def login_access_token():
    body = request.get_json(force=True)
    request_token = body.get("request_token") or session.get("request_token")
    if not request_token:
        return jsonify(error="No request_token yet — complete the Authorise step first"), 400
    if not API_SECRET:
        return jsonify(error="HDFC_SKY_API_SECRET is not set in .env"), 400
    raw = hdfc_client.get_access_token(API_KEY, request_token, API_SECRET, TIMEOUT)
    access_token = _extract(raw, "access_token", "accessToken")
    client_id = _extract(raw, "client_id", "clientId") or DEFAULT_CLIENT_ID
    if access_token:
        session["access_token"] = access_token
        session["client_id"] = client_id
    return jsonify(raw=raw, access_token_received=bool(access_token))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


# --- LTP (read-only, never dry-run gated) -----------------------------

@app.post("/api/ltp")
def ltp():
    unauth = _require_login()
    if unauth:
        return unauth
    watchlist = request.get_json(force=True).get("data", [])
    raw = hdfc_client.fetch_ltp(API_KEY, session["access_token"], watchlist, TIMEOUT)
    return jsonify(raw=raw)


# --- Orders: Regular -------------------------------------------------

@app.post("/api/orders/regular")
def place_regular():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "POST", "path": "/oapi/v1/orders", "body": {**order, "execution_type": "REGULAR"}},
        hdfc_client.place_regular_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.put("/api/orders/regular")
def modify_regular():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "PUT", "path": "/oapi/v1/orders", "body": {**order, "execution_type": "REGULAR"}},
        hdfc_client.modify_regular_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.delete("/api/orders/regular/<oms_order_id>")
def cancel_regular(oms_order_id):
    unauth = _require_login()
    if unauth:
        return unauth
    client_id = request.args.get("client_id") or session.get("client_id", DEFAULT_CLIENT_ID)
    return _mutate(
        {"method": "DELETE", "path": f"/oapi/v1/orders/{oms_order_id}", "client_id": client_id, "execution_type": "REGULAR"},
        hdfc_client.cancel_regular_order, API_KEY, session["access_token"], oms_order_id, client_id, TIMEOUT,
    )


# --- Orders: AMO -------------------------------------------------

@app.post("/api/orders/amo")
def place_amo():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "POST", "path": "/oapi/v1/orders", "body": {**order, "execution_type": "AMO"}},
        hdfc_client.place_amo_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.put("/api/orders/amo")
def modify_amo():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "PUT", "path": "/oapi/v1/orders", "body": {**order, "execution_type": "AMO"}},
        hdfc_client.modify_amo_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.delete("/api/orders/amo/<oms_order_id>")
def cancel_amo(oms_order_id):
    unauth = _require_login()
    if unauth:
        return unauth
    client_id = request.args.get("client_id") or session.get("client_id", DEFAULT_CLIENT_ID)
    return _mutate(
        {"method": "DELETE", "path": f"/oapi/v1/orders/kart/{oms_order_id}", "client_id": client_id, "execution_type": "AMO"},
        hdfc_client.cancel_amo_order, API_KEY, session["access_token"], oms_order_id, client_id, TIMEOUT,
    )


# --- Orders: Cover -------------------------------------------------

@app.post("/api/orders/cover")
def place_cover():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "POST", "path": "/oapi/v1/orders/kart", "body": {**order, "execution_type": "CO"}},
        hdfc_client.place_cover_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.put("/api/orders/cover")
def modify_cover():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "PUT", "path": "/oapi/v1/orders/kart", "body": {**order, "execution_type": "CO"}},
        hdfc_client.modify_cover_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.delete("/api/orders/cover/<oms_order_id>")
def cancel_cover(oms_order_id):
    unauth = _require_login()
    if unauth:
        return unauth
    body = request.get_json(force=True)
    return _mutate(
        {"method": "DELETE", "path": f"/oapi/v1/orders/kart/{oms_order_id}", "body": {**body, "execution_type": "CO"}},
        hdfc_client.cancel_cover_order, API_KEY, session["access_token"], oms_order_id, body, TIMEOUT,
    )


# --- Orders: Bracket -------------------------------------------------

@app.post("/api/orders/bracket")
def place_bracket():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "POST", "path": "/oapi/v1/orders/kart", "body": {**order, "execution_type": "BO"}},
        hdfc_client.place_bracket_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.put("/api/orders/bracket")
def modify_bracket():
    unauth = _require_login()
    if unauth:
        return unauth
    order = request.get_json(force=True)
    return _mutate(
        {"method": "PUT", "path": "/oapi/v1/orders/kart", "body": {**order, "execution_type": "BO"}},
        hdfc_client.modify_bracket_order, API_KEY, session["access_token"], order, TIMEOUT,
    )


@app.delete("/api/orders/bracket/<oms_order_id>")
def exit_bracket(oms_order_id):
    unauth = _require_login()
    if unauth:
        return unauth
    body = request.get_json(force=True)
    return _mutate(
        {"method": "DELETE", "path": f"/oapi/v1/orders/kart/{oms_order_id}", "body": {**body, "execution_type": "BO"}},
        hdfc_client.exit_bracket_order, API_KEY, session["access_token"], oms_order_id, body, TIMEOUT,
    )


# --- Orders: GTT -------------------------------------------------
# Modify GTT is not exposed: HDFC's doc gives no body/identifier for it.

@app.post("/api/orders/gtt")
def place_gtt():
    unauth = _require_login()
    if unauth:
        return unauth
    gtt = request.get_json(force=True)
    return _mutate(
        {"method": "POST", "path": "/oapi/v1/event/gtt", "body": gtt},
        hdfc_client.place_gtt_order, API_KEY, session["access_token"], gtt, TIMEOUT,
    )


@app.delete("/api/orders/gtt/<client_id>/<gtt_id>")
def cancel_gtt(client_id, gtt_id):
    unauth = _require_login()
    if unauth:
        return unauth
    return _mutate(
        {"method": "DELETE", "path": f"/oapi/v1/event/gtt/{client_id}/{gtt_id}"},
        hdfc_client.cancel_gtt_order, API_KEY, session["access_token"], client_id, gtt_id, TIMEOUT,
    )


@app.get("/api/orders/gtt/<client_id>")
def fetch_gtt(client_id):
    unauth = _require_login()
    if unauth:
        return unauth
    return jsonify(raw=hdfc_client.fetch_gtt_orders(API_KEY, session["access_token"], client_id, TIMEOUT))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
