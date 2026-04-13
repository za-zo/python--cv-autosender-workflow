"""Step 5 - Four free keyless APIs (run concurrently)."""

import concurrent.futures

from email_verifier.logger import Logger
from email_verifier.api_services import (
    check_disify,
    check_kickbox,
    check_debounce,
    check_validator_pizza,
)


class StepApiChecks:
    STEP = 5
    NAME = "API checks (×4, async)"

    def run(self, email: str, domain: str) -> dict:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(check_disify, email): "Disify",
                pool.submit(check_kickbox, domain): "Kickbox",
                pool.submit(check_debounce, email): "DeBounce",
                pool.submit(check_validator_pizza, domain): "ValidatorPizza",
            }
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        reject_reason = None
        lines = []

        for res in sorted(results, key=lambda r: r["api"]):
            api = res["api"]
            if not res["available"]:
                err = res.get("error", "unavailable")
                lines.append(f"  {Logger.color('─', 'gray')} {Logger.color(api, 'gray'):<18} skipped ({err})")
            elif res["disposable"]:
                lines.append(f"  {Logger.color('✗', 'red')} {Logger.color(api, 'red'):<18} flagged as disposable")
                if reject_reason is None:
                    reject_reason = f"disposable_{api.lower()}"
            else:
                lines.append(f"  {Logger.color('✓', 'green')} {Logger.color(api, 'green'):<18} not disposable")

        if reject_reason:
            Logger.step(self.STEP, self.NAME, False, "at least one API flagged disposable")
            print("\n".join(lines))
            return {"passed": False, "reason": reject_reason}

        available_count = sum(1 for r in results if r["available"])
        if available_count == 0:
            Logger.step(self.STEP, self.NAME, True, "all APIs unavailable — trusting MX records")
        else:
            Logger.step(
                self.STEP, self.NAME, True, f"not disposable ({available_count}/4 APIs responded)"
            )
        print("\n".join(lines))
        return {"passed": True}