from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINTS_FILE = REPO_ROOT / "config" / "endpoints.yaml"


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_secret: str
    client_id: str
    password: str
    totp_secret: str
    base_url: str
    request_timeout_seconds: float
    session_file: str
    dry_run: bool
    endpoints: dict


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def load_settings(env_file: str | Path | None = None,
                   endpoints_file: str | Path = DEFAULT_ENDPOINTS_FILE) -> Settings:
    load_dotenv(env_file)

    with open(endpoints_file, "r") as f:
        endpoints = yaml.safe_load(f)

    return Settings(
        api_key=_require("HDFC_SKY_API_KEY"),
        api_secret=_require("HDFC_SKY_API_SECRET"),
        client_id=_require("HDFC_SKY_CLIENT_ID"),
        password=_require("HDFC_SKY_PASSWORD"),
        totp_secret=os.environ.get("HDFC_SKY_TOTP_SECRET", ""),
        base_url=os.environ.get("HDFC_SKY_BASE_URL", endpoints.get("base_url", "")),
        request_timeout_seconds=float(os.environ.get("HDFC_SKY_REQUEST_TIMEOUT_SECONDS", "10")),
        session_file=os.environ.get("HDFC_SKY_SESSION_FILE", ".session.json"),
        dry_run=os.environ.get("DRY_RUN", "true").strip().lower() in ("1", "true", "yes"),
        endpoints=endpoints,
    )
