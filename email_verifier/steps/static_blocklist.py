"""Step 2 - Static blocklist check."""

from email_verifier.blocklist import StaticBlocklist
from email_verifier.logger import Logger


class StepStaticBlocklist:
    STEP = 2
    NAME = "Static blocklist (×3)"

    def __init__(self, blocklist: StaticBlocklist):
        self.blocklist = blocklist

    def run(self, domain: str) -> dict:
        if self.blocklist.contains(domain):
            Logger.step(self.STEP, self.NAME, False, f"{domain} found in merged blocklist")
            return {"passed": False, "reason": "disposable_static_list"}

        Logger.step(
            self.STEP,
            self.NAME,
            True,
            f"{domain} not in merged blocklist ({len(self.blocklist.domains):,} entries)",
        )
        return {"passed": True}