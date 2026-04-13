"""Kickbox API service."""

import requests

from email_verifier.config import Config


def check_kickbox(domain: str) -> dict:
    try:
        r = requests.get(
            f"https://open.kickbox.com/v1/disposable/{domain}",
            timeout=Config.API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return {
            "api": "Kickbox",
            "disposable": bool(data.get("disposable", False)),
            "available": True,
        }
    except Exception as e:
        return {"api": "Kickbox", "available": False, "error": str(e)}