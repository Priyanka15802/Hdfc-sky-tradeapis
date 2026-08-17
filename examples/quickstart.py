"""Minimal end-to-end example: log in, then place one normal order.

Run with DRY_RUN=true (the .env.example default) first — it prints the
exact request that *would* be sent instead of sending it, so you can
sanity-check the payload against the real HDFC Sky docs before risking a
live order.
"""
from __future__ import annotations

from hdfc_sky import AuthClient, OrderClient, load_settings
from hdfc_sky.http_client import HttpClient


def main() -> None:
    settings = load_settings()
    http = HttpClient(settings.base_url, timeout=settings.request_timeout_seconds)

    auth = AuthClient(http, settings)
    auth.login()

    orders = OrderClient(http, settings)
    result = orders.place_normal_order(
        symbol="RELIANCE-EQ",
        exchange="NSE",
        transaction_type="BUY",
        order_type="LIMIT",
        quantity=1,
        price=0,
        product="CNC",
    )
    print(result)


if __name__ == "__main__":
    main()
