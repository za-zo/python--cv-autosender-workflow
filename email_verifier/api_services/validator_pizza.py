"""Validator.pizza API service."""

import requests

from email_verifier.config import Config


def check_validator_pizza(domain: str) -> dict:
    try:
        r = requests.get(
            f"https://www.validator.pizza/domain/{domain}",
            timeout=Config.API_TIMEOUT
        )
        if r.status_code == 429:
            return {"api": "ValidatorPizza", "available": False, "error": "rate limit reached (120 req/h)"}
        r.raise_for_status()
        data = r.json()
        return {
            "api": "ValidatorPizza",
            "disposable": bool(data.get("disposable", False)),
            "available": True,
        }
    except Exception as e:
        return {"api": "ValidatorPizza", "available": False, "error": str(e)}