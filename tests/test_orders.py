from unittest.mock import MagicMock

import pytest

from hdfc_sky.config import Settings
from hdfc_sky.orders import OrderClient

ENDPOINTS = {
    "orders": {
        "normal": {
            "place": {"method": "POST", "path": "/oapi/v1/orders/normal"},
            "modify": {"method": "PUT", "path": "/oapi/v1/orders/normal/{order_id}"},
            "cancel": {"method": "DELETE", "path": "/oapi/v1/orders/normal/{order_id}"},
        },
        "cover": {
            "place": {"method": "POST", "path": "/oapi/v1/orders/cover"},
            "modify": {"method": "PUT", "path": "/oapi/v1/orders/cover/{order_id}"},
            "cancel": {"method": "DELETE", "path": "/oapi/v1/orders/cover/{order_id}"},
        },
        "bracket": {
            "place": {"method": "POST", "path": "/oapi/v1/orders/bracket"},
            "modify": {"method": "PUT", "path": "/oapi/v1/orders/bracket/{order_id}"},
            "cancel": {"method": "DELETE", "path": "/oapi/v1/orders/bracket/{order_id}"},
        },
    }
}


def make_settings(dry_run: bool) -> Settings:
    return Settings(
        api_key="k", api_secret="s", client_id="c", password="p", totp_secret="",
        base_url="https://api.hdfcsky.com", request_timeout_seconds=10,
        session_file=".session.json", dry_run=dry_run, endpoints=ENDPOINTS,
    )


def test_place_normal_order_dry_run_does_not_hit_network():
    http = MagicMock()
    orders = OrderClient(http, make_settings(dry_run=True))

    result = orders.place_normal_order(symbol="RELIANCE-EQ", quantity=1)

    http.request.assert_not_called()
    assert result == {
        "dry_run": True,
        "method": "POST",
        "path": "/oapi/v1/orders/normal",
        "payload": {"symbol": "RELIANCE-EQ", "quantity": 1},
    }


def test_cancel_bracket_order_formats_order_id_into_path():
    http = MagicMock()
    http.request.return_value = {"status": "cancelled"}
    orders = OrderClient(http, make_settings(dry_run=False))

    result = orders.cancel_bracket_order(order_id="ORD123")

    http.request.assert_called_once_with("DELETE", "/oapi/v1/orders/bracket/ORD123")
    assert result == {"status": "cancelled"}


@pytest.mark.parametrize("order_type", ["normal", "cover", "bracket"])
@pytest.mark.parametrize("action", ["place", "modify", "cancel"])
def test_every_order_type_and_action_is_wired_up(order_type, action):
    http = MagicMock()
    http.request.return_value = {}
    orders = OrderClient(http, make_settings(dry_run=False))

    method = getattr(orders, f"{action}_{order_type}_order")
    if action == "place":
        method(symbol="X")
    else:
        method(order_id="ORD1")

    assert http.request.called
