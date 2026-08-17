"""Flask backend for the HDFC Sky lite trading tool.

Keeps api_key/api_secret/consent server-side (from .env) and the per-login
token_id/request_token/access_token in the server-side session — none of
that ever reaches browser JS directly except access_token's presence
(true/false), so the frontend can tell if it's logged in.

Only 3 login steps are user-facing (Client ID, OTP, MPIN) — Get Token ID
and Authorise still happen, chained in behind /api/login/begin and
/api/login/finish respectively, since they're required by HDFC's flow but
don't need their own screen.

HDFC's docs never show response bodies, so this file doesn't assume a
fixed shape for them: `_extract` tries a handful of common key spellings
and otherwise leaves the field blank for the user to fill in by hand after
looking at the raw response (echoed back as "raw" in login replies).

Order-mutating calls (place/modify/cancel, everywhere) are gated by
dry-run, which defaults to DRY_RUN from .env but can be flipped live per
session via POST /api/dry-run: with it on, the exact request that *would*
be sent is returned instead of actually sending it.
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
CONSENT = os.environ.get("HDFC_SKY_CONSENT", "")
TIMEOUT = float(os.environ.get("HDFC_SKY_REQUEST_TIMEOUT_SECONDS", "10"))
DRY_RUN_DEFAULT = os.environ.get("DRY_RUN", "true").strip().lower() in ("1", "true", "yes")


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


def _dry_run() -> bool:
    """Effective dry-run state: a per-session toggle if set, else the
    .env default. Every new browser session starts from the .env value,
    so the tool opens safe even if you forget to check."""
    return session.get("dry_run", DRY_RUN_DEFAULT)


def _mutate(description: dict, fn, *args):
    """Runs an order-mutating HDFC call, or short-circuits under dry-run."""
    if _dry_run():
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
        dry_run=_dry_run(),
    )


@app.post("/api/dry-run")
def set_dry_run():
    body = request.get_json(force=True)
    session["dry_run"] = bool(body.get("enabled"))
    return jsonify(dry_run=_dry_run())


# --- Login flow -------------------------------------------------
#
# Only 3 steps are user-facing: Client ID, OTP, MPIN. HDFC's Get Token ID
# and Authorise are still called (they're required), just chained
# server-side instead of needing their own buttons. Authorise's `consent`
# value comes from HDFC_SKY_CONSENT in .env rather than being typed in.

@app.post("/api/login/begin")
def login_begin():
    if not API_KEY:
        return jsonify(error="HDFC_SKY_API_KEY is not set in .env"), 400
    username = request.get_json(force=True)["username"]

    token_raw = hdfc_client.get_token_id(API_KEY, TIMEOUT)
    token_id = _extract(token_raw, "token_id", "tokenId")
    if not token_id:
        return jsonify(error="Could not start login (no token_id in response)", raw=token_raw), 502
    session["token_id"] = token_id

    try:
        username_raw = hdfc_client.validate_username(API_KEY, token_id, username, TIMEOUT)
    except HdfcApiError as e:
        return jsonify(error="HDFC Sky API error", status_code=e.status_code, payload=e.payload), 502

    return jsonify(ok=True, raw={"token_id": token_raw, "username": username_raw})


@app.post("/api/login/otp")
def login_otp():
    body = request.get_json(force=True)
    token_id = session.get("token_id") or body.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — start over from Client ID"), 400
    raw = hdfc_client.validate_otp(API_KEY, token_id, body["otp"], TIMEOUT)
    return jsonify(ok=True, raw=raw)


@app.post("/api/login/otp/resend")
def login_otp_resend():
    token_id = session.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — start over from Client ID"), 400
    raw = hdfc_client.resend_otp(API_KEY, token_id, TIMEOUT)
    return jsonify(raw=raw)


@app.post("/api/login/finish")
def login_finish():
    """Validate MPIN, then chain Authorise + Get Access Token automatically."""
    body = request.get_json(force=True)
    token_id = session.get("token_id")
    if not token_id:
        return jsonify(error="No token_id yet — start over from Client ID"), 400
    if not CONSENT:
        return jsonify(error="HDFC_SKY_CONSENT is not set in .env"), 400
    if not API_SECRET:
        return jsonify(error="HDFC_SKY_API_SECRET is not set in .env"), 400

    try:
        pin_raw = hdfc_client.validate_pin(API_KEY, token_id, body["answer"], TIMEOUT)
    except HdfcApiError as e:
        return jsonify(error="HDFC Sky API error at Validate MPIN", status_code=e.status_code, payload=e.payload), 502
    request_token = _extract(pin_raw, "request_token", "requestToken")
    if not request_token:
        return jsonify(error="No request_token in Validate MPIN response", raw=pin_raw), 502

    try:
        authorise_raw = hdfc_client.authorise(API_KEY, token_id, CONSENT, request_token, TIMEOUT)
    except HdfcApiError as e:
        return jsonify(error="HDFC Sky API error at Authorise", status_code=e.status_code, payload=e.payload), 502
    request_token = _extract(authorise_raw, "request_token", "requestToken") or request_token

    try:
        token_raw = hdfc_client.get_access_token(API_KEY, request_token, API_SECRET, TIMEOUT)
    except HdfcApiError as e:
        return jsonify(error="HDFC Sky API error at Get Access Token", status_code=e.status_code, payload=e.payload), 502
    access_token = _extract(token_raw, "access_token", "accessToken")
    client_id = _extract(token_raw, "client_id", "clientId") or DEFAULT_CLIENT_ID
    if not access_token:
        return jsonify(error="No access_token in Get Access Token response", raw=token_raw), 502

    session["access_token"] = access_token
    session["client_id"] = client_id
    return jsonify(ok=True, logged_in=True, client_id=client_id,
                    raw={"pin": pin_raw, "authorise": authorise_raw, "access_token": token_raw})


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
