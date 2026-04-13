"""Step 4 - Provider check."""

from email_verifier.config import Config
from email_verifier.logger import Logger


class StepProvider:
    STEP = 4
    NAME = "Provider check"

    def run(self, domain: str, mx_server: str) -> dict:
        mx_parts = mx_server.split(".")
        mx_domain_2 = ".".join(mx_parts[-2:]) if len(mx_parts) >= 2 else mx_server
        mx_domain_3 = ".".join(mx_parts[-3:]) if len(mx_parts) >= 3 else mx_domain_2

        is_major = (
            domain in Config.MAJOR_PROVIDERS
            or mx_domain_2 in Config.TRUSTED_MX_PROVIDERS
            or mx_domain_3 in Config.TRUSTED_MX_PROVIDERS
        )

        if is_major:
            if domain in Config.MAJOR_PROVIDERS:
                label = f"{domain} is a major provider"
            else:
                label = f"hosted on {mx_server} (Google WS / Zoho / M365)"
            Logger.step(self.STEP, self.NAME, True, f"{label} — trusted infrastructure")
            return {"passed": True, "is_major_provider": True}

        Logger.skip(
            self.STEP, self.NAME, f"{domain} is not a major provider (MX: {mx_server})"
        )
        return {"passed": True, "is_major_provider": False}