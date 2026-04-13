"""Step 3 - DNS/MX records check."""

import dns.resolver

from email_verifier.config import Config
from email_verifier.logger import Logger


class StepDNS:
    STEP = 3
    NAME = "DNS / MX records"

    def run(self, domain: str) -> dict:
        try:
            mx_records = dns.resolver.resolve(domain, "MX", lifetime=Config.DNS_TIMEOUT)
            servers = sorted([(r.preference, str(r.exchange).rstrip(".")) for r in mx_records])
            mx_server = servers[0][1]
            Logger.step(self.STEP, self.NAME, True, f"MX found → {mx_server}")
            return {"passed": True, "mx_server": mx_server}

        except dns.resolver.NXDOMAIN:
            Logger.step(self.STEP, self.NAME, False, f"Domain {domain} does not exist")
            return {"passed": False, "reason": "domain_not_found"}

        except dns.resolver.NoAnswer:
            Logger.step(self.STEP, self.NAME, False, f"No MX records for {domain}")
            return {"passed": False, "reason": "no_mx_records"}

        except dns.resolver.Timeout:
            Logger.step(self.STEP, self.NAME, False, "DNS resolution timed out")
            return {"passed": False, "reason": "dns_timeout"}

        except Exception as e:
            Logger.step(self.STEP, self.NAME, False, str(e))
            return {"passed": False, "reason": f"dns_error: {e}"}