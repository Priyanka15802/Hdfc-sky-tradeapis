"""Verifies every hdfc_client function hits the exact URL/method/host/body
documented in HDFC's own curl examples. requests.request is mocked so
nothing touches the network.
"""
from unittest.mock import MagicMock, patch

import hdfc_client as hc


def _mock_response(json_body=None, status=200):
    resp = MagicMock()
    resp.ok = status < 400
    resp.status_code = status
    resp.content = b"{}" if json_body is not None else b""
    resp.json.return_value = json_body or {}
    return resp


@patch("hdfc_client.requests.request")
def test_get_token_id(mock_req):
    mock_req.return_value = _mock_response({"token_id": "T1"})
    hc.get_token_id("KEY", 10)
    args, kwargs = mock_req.call_args
    assert args[0] == "GET"
    assert args[1] == "https://developer.hdfcsky.com/oapi/v1/login?api_key=KEY"


@patch("hdfc_client.requests.request")
def test_validate_otp_hits_prod_host(mock_req):
    # Overridden from HDFC's doc (which shows UAT here) after live testing
    # showed a 401 "invalid login attempt" — see the comment in
    # hdfc_client.validate_otp for the full reasoning.
    mock_req.return_value = _mock_response({})
    hc.validate_otp("KEY", "TOK", "1234", 10)
    args, kwargs = mock_req.call_args
    assert args[0] == "PUT"
    assert args[1] == "https://developer.hdfcsky.com/oapi/v1/otp/validate?api_key=KEY&token_id=TOK"
    assert kwargs["json"] == {"otp": "1234"}


@patch("hdfc_client.requests.request")
def test_access_token_body(mock_req):
    mock_req.return_value = _mock_response({"access_token": "AT"})
    hc.get_access_token("KEY", "REQ", "SECRET", 10)
    args, kwargs = mock_req.call_args
    assert "access-token?api_key=KEY&request_token=REQ" in args[1]
    assert kwargs["json"] == {"apiSecret": "SECRET"}


@patch("hdfc_client.requests.request")
def test_place_regular_order_sets_execution_type(mock_req):
    mock_req.return_value = _mock_response({"oms_order_id": "1"})
    hc.place_regular_order("KEY", "TOKEN", {"exchange": "NSE", "quantity": 1}, 10)
    args, kwargs = mock_req.call_args
    assert args[0] == "POST"
    assert args[1] == "https://developer.hdfcsky.com/oapi/v1/orders?api_key=KEY"
    assert kwargs["json"]["execution_type"] == "REGULAR"
    assert kwargs["headers"]["Authorization"] == "TOKEN"


@patch("hdfc_client.requests.request")
def test_cancel_amo_order_uses_kart_path(mock_req):
    mock_req.return_value = _mock_response({})
    hc.cancel_amo_order("KEY", "TOKEN", "OMS1", "CID", 10)
    args, kwargs = mock_req.call_args
    assert args[0] == "DELETE"
    assert args[1] == "https://developer.hdfcsky.com/oapi/v1/orders/kart/OMS1?api_key=KEY&client_id=CID&execution_type=AMO"


@patch("hdfc_client.requests.request")
def test_cancel_cover_order_sends_body(mock_req):
    mock_req.return_value = _mock_response({})
    hc.cancel_cover_order("KEY", "TOKEN", "OMS1", {"client_id": "CID"}, 10)
    args, kwargs = mock_req.call_args
    assert args[0] == "DELETE"
    assert kwargs["json"]["execution_type"] == "CO"
    assert kwargs["json"]["client_id"] == "CID"


@patch("hdfc_client.requests.request")
def test_place_gtt_hits_uat_host(mock_req):
    mock_req.return_value = _mock_response({})
    hc.place_gtt_order("KEY", "TOKEN", {"action_type": "single_order"}, 10)
    args, kwargs = mock_req.call_args
    assert args[1] == "https://uat-developer.hdfcsky.com/oapi/v1/event/gtt?api_key=KEY"


@patch("hdfc_client.requests.request")
def test_fetch_ltp_wraps_watchlist_in_data(mock_req):
    mock_req.return_value = _mock_response({"data": []})
    hc.fetch_ltp("KEY", "TOKEN", [{"exchange": "BSE", "token": "542809"}], 10)
    args, kwargs = mock_req.call_args
    assert args[0] == "PUT"
    assert args[1] == "https://uat-developer.hdfcsky.com/oapi/v1/fetch-ltp?api_key=KEY"
    assert kwargs["json"] == {"data": [{"exchange": "BSE", "token": "542809"}]}


@patch("hdfc_client.requests.request")
def test_error_response_raises(mock_req):
    mock_req.return_value = _mock_response({"error": "bad"}, status=400)
    try:
        hc.get_token_id("KEY", 10)
        assert False, "expected HdfcApiError"
    except hc.HdfcApiError as e:
        assert e.status_code == 400
