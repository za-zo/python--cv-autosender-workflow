"""Disify API service."""

import requests

from email_verifier.config import Config


def check_disify(email: str) -> dict:
    try:
        r = requests.get(
            f"https://www.disify.com/api/email/{email}",
            timeout=Config.API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return {
            "api": "Disify",
            "disposable": bool(data.get("disposable", False)),
            "available": True,
        }
    except Exception as e:
        return {"api": "Disify", "available": False, "error": str(e)}