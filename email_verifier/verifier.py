"""Main EmailVerifier class - orchestrates all verification steps."""

from email_verifier.blocklist import StaticBlocklist
from email_verifier.logger import Logger
from email_verifier.steps import (
    StepSyntax,
    StepStaticBlocklist,
    StepDNS,
    StepProvider,
    StepApiChecks,
)


class EmailVerifier:
    def __init__(self):
        blocklist = StaticBlocklist()
        self.step_syntax = StepSyntax()
        self.step_list = StepStaticBlocklist(blocklist)
        self.step_dns = StepDNS()
        self.step_prov = StepProvider()
        self.step_apis = StepApiChecks()

    def _skip_from(self, from_step: int):
        steps = {
            2: ("Static blocklist (×3)", StepStaticBlocklist),
            3: ("DNS / MX records", StepDNS),
            4: ("Provider check", StepProvider),
            5: ("API checks (×4, async)", StepApiChecks),
        }
        for number, (name, _) in steps.items():
            if number >= from_step:
                Logger.skip(number, name, "skipped")

    def _reject(self, reason: str) -> dict:
        Logger.footer(False, reason)
        return {"valid": False, "reason": reason}

    def _accept(self, reason: str) -> dict:
        Logger.footer(True, reason)
        return {"valid": True, "reason": reason}

    def verify(self, email: str) -> dict:
        Logger.header(email)

        s1 = self.step_syntax.run(email)
        if not s1["passed"]:
            self._skip_from(2)
            return self._reject(s1["reason"])

        email = s1["email"]
        domain = email.split("@")[1]

        s2 = self.step_list.run(domain)
        if not s2["passed"]:
            self._skip_from(3)
            return self._reject(s2["reason"])

        s3 = self.step_dns.run(domain)
        if not s3["passed"]:
            self._skip_from(4)
            return self._reject(s3["reason"])

        mx_server = s3["mx_server"]

        s4 = self.step_prov.run(domain, mx_server)
        if s4["is_major_provider"]:
            Logger.skip(5, "API checks (×4, async)", "skipped — major provider trusted")
            return self._accept("major_provider_trusted")

        s5 = self.step_apis.run(email, domain)
        if not s5["passed"]:
            return self._reject(s5["reason"])

        return self._accept("all_checks_passed")

    def check(self, email: str) -> bool:
        return self.verify(email)["valid"]