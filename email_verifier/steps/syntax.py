"""Step 1 - Syntax validation."""

from email_validator import validate_email, EmailNotValidError
from email_verifier.logger import Logger


class StepSyntax:
    STEP = 1
    NAME = "Syntax"

    def run(self, email: str) -> dict:
        try:
            result = validate_email(email, check_deliverability=False)
            normalized = result.normalized
            Logger.step(self.STEP, self.NAME, True, f"Valid format → {normalized}")
            return {"passed": True, "email": normalized}
        except EmailNotValidError as e:
            Logger.step(self.STEP, self.NAME, False, str(e))
            return {"passed": False, "reason": f"invalid_syntax: {e}"}