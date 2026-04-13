"""DeBounce API service."""

import requests

from email_verifier.config import Config


def check_debounce(email: str) -> dict:
    try:
        r = requests.get(
            f"https://disposable.debounce.io/?email={email}",
            timeout=Config.API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        raw = data.get("disposable", "false")
        is_disposable = str(raw).lower() == "true"
        return {
            "api": "DeBounce",
            "disposable": is_disposable,
            "available": True,
        }
    except Exception as e:
        return {"api": "DeBounce", "available": False, "error": str(e)}