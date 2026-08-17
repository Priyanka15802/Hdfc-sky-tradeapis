class HdfcSkyError(Exception):
    """Base class for every error raised by this client."""


class APIError(HdfcSkyError):
    """The API responded with a non-2xx status code."""

    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"HDFC Sky API error {status_code}: {payload}")


class AuthenticationError(HdfcSkyError):
    """Login/session flow failed."""


class OrderError(HdfcSkyError):
    """Order placement/modification/cancellation failed."""
