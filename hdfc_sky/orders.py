from __future__ import annotations

from .config import Settings
from .exceptions import OrderError
from .http_client import HttpClient

ORDER_TYPES = ("normal", "cover", "bracket")


class OrderClient:
    """Place/modify/cancel normal, cover, and bracket orders.

    Like AuthClient, every endpoint is read from config/endpoints.yaml
    (under `orders.<normal|cover|bracket>.<place|modify|cancel>`), so a
    wrong path is a one-line config fix, not a code change.

    When settings.dry_run is True (the default), requests are NOT sent —
    the method/path/payload are returned as a dict instead. Only flip
    DRY_RUN=false once you've verified the endpoints/payload shape against
    the real HDFC Sky Open API docs.
    """

    def __init__(self, http: HttpClient, settings: Settings):
        self.http = http
        self.settings = settings

    def _action(self, order_type: str, action: str, order_id: str | None = None, **payload) -> dict:
        if order_type not in ORDER_TYPES:
            raise OrderError(f"Unknown order type: {order_type}")

        endpoint = self.settings.endpoints["orders"][order_type][action]
        path = endpoint["path"].format(order_id=order_id) if order_id else endpoint["path"]
        method = endpoint["method"]

        if self.settings.dry_run:
            return {"dry_run": True, "method": method, "path": path, "payload": payload}

        kwargs = {"json": payload} if payload else {}
        return self.http.request(method, path, **kwargs)

    # --- normal orders -------------------------------------------------

    def place_normal_order(self, **order_params) -> dict:
        return self._action("normal", "place", **order_params)

    def modify_normal_order(self, order_id: str, **order_params) -> dict:
        return self._action("normal", "modify", order_id=order_id, **order_params)

    def cancel_normal_order(self, order_id: str) -> dict:
        return self._action("normal", "cancel", order_id=order_id)

    # --- cover orders -------------------------------------------------

    def place_cover_order(self, **order_params) -> dict:
        return self._action("cover", "place", **order_params)

    def modify_cover_order(self, order_id: str, **order_params) -> dict:
        return self._action("cover", "modify", order_id=order_id, **order_params)

    def cancel_cover_order(self, order_id: str) -> dict:
        return self._action("cover", "cancel", order_id=order_id)

    # --- bracket orders -------------------------------------------------

    def place_bracket_order(self, **order_params) -> dict:
        return self._action("bracket", "place", **order_params)

    def modify_bracket_order(self, order_id: str, **order_params) -> dict:
        return self._action("bracket", "modify", order_id=order_id, **order_params)

    def cancel_bracket_order(self, order_id: str) -> dict:
        return self._action("bracket", "cancel", order_id=order_id)
