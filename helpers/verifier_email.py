"""
=============================================================================
EMAIL VERIFIER
=============================================================================
Checks an email address through 6 steps before generating an AI message
or sending via Gmail — saving tokens and Gmail quota.

Install :
    pip install email-validator dnspython requests

Usage :
    from verifier_email import EmailVerifier

    verifier = EmailVerifier()
    if verifier.check("someone@company.com"):
        # generate AI message + send Gmail
    else:
        # skip — 0 tokens, 0 Gmail quota used

Steps :
    1. Syntax          — is the format valid ?
    2. Static list     — is the domain in the +100k blocklist ?
    3. DNS / MX        — does the domain have a mail server ?
    4. Provider        — is it Gmail / Google Workspace / Zoho / Microsoft 365 ?
                         ↳ YES → accept immediately, skip Steps 5 & 6
    5. Disify API      — is it a disposable domain ? (free, no key)
    6. Kickbox API     — second opinion on disposable domains (free, no key)
=============================================================================
"""

import requests
import dns.resolver
from email_validator import validate_email, EmailNotValidError


# =============================================================================
# LOGGER — handles all terminal output with colors
# =============================================================================

class Logger:

    COLORS = {
        "green"  : "\033[92m",
        "red"    : "\033[91m",
        "yellow" : "\033[93m",
        "cyan"   : "\033[96m",
        "white"  : "\033[97m",
        "gray"   : "\033[90m",
        "bold"   : "\033[1m",
        "reset"  : "\033[0m",
    }

    @staticmethod
    def color(text: str, color: str) -> str:
        code = Logger.COLORS.get(color, "")
        return f"{code}{text}{Logger.COLORS['reset']}"

    @staticmethod
    def header(email: str):
        print(f"\n{'─' * 65}")
        print(f"  {Logger.color('▶', 'cyan')} {Logger.color(email, 'bold')}")
        print(f"{'─' * 65}")

    @staticmethod
    def step(number: int, name: str, passed: bool, message: str):
        icon   = Logger.color("✓", "green") if passed else Logger.color("✗", "red")
        label  = Logger.color(f"[Step {number}]", "cyan")
        name   = Logger.color(f"{name:<22}", "white")
        detail = Logger.color(message, "green") if passed else Logger.color(message, "red")
        print(f"   {label} {icon}  {name} {detail}")

    @staticmethod
    def skip(number: int, name: str, reason: str):
        label  = Logger.color(f"[Step {number}]", "cyan")
        name   = Logger.color(f"{name:<22}", "gray")
        reason = Logger.color(f"— {reason}", "gray")
        print(f"   {label} -  {name} {reason}")

    @staticmethod
    def footer(valid: bool, reason: str):
        if valid:
            result = Logger.color("✅  VALID   → Generate AI message + Send Gmail", "green")
        else:
            result = Logger.color("❌  SKIPPED → 0 token consumed, 0 Gmail quota used", "red")
        print(f"\n   {Logger.color('Result:', 'bold')} {result}")
        print(f"   {Logger.color('Reason:', 'bold')} {Logger.color(reason, 'gray')}")

    @staticmethod
    def summary(total: int, valid: int, skipped: int):
        savings = round(skipped / total * 100) if total > 0 else 0
        print(f"\n{Logger.color('═' * 65, 'cyan')}")
        print(Logger.color("  SUMMARY", "bold"))
        print(Logger.color("─" * 65, "cyan"))
        print(f"  {'Total checked':<25} {Logger.color(str(total), 'white')}")
        print(f"  {'Valid (processed)':<25} {Logger.color(str(valid), 'green')}")
        print(f"  {'Skipped (blocked)':<25} {Logger.color(str(skipped), 'red')}")
        print(f"  {'Savings':<25} {Logger.color(str(savings) + '%', 'yellow')}  <- tokens + Gmail quota saved")
        print(Logger.color("═" * 65, "cyan") + "\n")


# =============================================================================
# CONFIG — all constants in one place
# =============================================================================

class Config:

    DNS_TIMEOUT = 5   # seconds before DNS resolution is aborted
    API_TIMEOUT = 6   # seconds before an API call is aborted

    # Fallback list if GitHub is unreachable at startup
    FALLBACK_BLOCKLIST = {
        "mailinator.com", "guerrillamail.com", "temp-mail.org", "yopmail.com",
        "trashmail.com", "fakeinbox.com", "10minutemail.com", "maildrop.cc",
        "throwaway.email", "discard.email", "spamgourmet.com", "tempr.email",
        "mohmal.com", "tempinbox.com", "dispostable.com", "sharklasers.com",
        "dependity.com", "emailondeck.com", "drrieca.com", "hostelness.com",
    }

    # Domains where SMTP verification is unreliable (they accept all then filter)
    MAJOR_PROVIDERS = {
        "gmail.com", "googlemail.com",
        "outlook.com", "hotmail.com", "live.com", "msn.com",
        "yahoo.com", "yahoo.fr", "yahoo.co.uk",
        "icloud.com", "me.com", "mac.com",
        "aol.com", "protonmail.com", "proton.me",
    }

    # MX server domains that indicate trusted hosting infrastructure
    # (companies using Google Workspace, Zoho, Microsoft 365, etc.)
    TRUSTED_MX_PROVIDERS = {
        "google.com",              # Google Workspace  -> aspmx.l.google.com
        "googlemail.com",          # Google Workspace  -> alt*.aspmx.l.google.com
        "outlook.com",             # Microsoft 365     -> *.mail.protection.outlook.com
        "protection.outlook.com",  # Microsoft 365
        "yahoodns.net",            # Yahoo Business
        "zoho.com",                # Zoho Mail         -> mx.zoho.com
        "zoho.in",                 # Zoho Mail India   -> mx.zoho.in
        "zoho.eu",                 # Zoho Mail Europe  -> mx.zoho.eu
        "mimecast.com",            # Mimecast (enterprise email filter)
        "pphosted.com",            # Proofpoint (enterprise email filter)
    }


# =============================================================================
# STATIC BLOCKLIST — loaded once at startup from GitHub
# =============================================================================

class StaticBlocklist:
    """
    Downloads and holds the +100k disposable domain blocklist from GitHub.
    Loaded once when EmailVerifier is instantiated.
    """

    GITHUB_URL = (
        "https://raw.githubusercontent.com/"
        "disposable-email-domains/disposable-email-domains/"
        "master/disposable_email_blocklist.conf"
    )

    def __init__(self):
        self.domains = self._load()

    def _load(self) -> set:
        try:
            response = requests.get(self.GITHUB_URL, timeout=10)
            response.raise_for_status()
            domains = set(response.text.strip().splitlines())
            print(f"[INIT] {len(domains)} disposable domains loaded from GitHub")
            return domains
        except Exception as e:
            print(f"[INIT] GitHub unreachable ({e}) -> using fallback list")
            return Config.FALLBACK_BLOCKLIST

    def contains(self, domain: str) -> bool:
        return domain in self.domains


# =============================================================================
# STEP 1 — SYNTAX
# =============================================================================

class StepSyntax:
    """
    Validates the email format using the email-validator library.
    Returns the normalized email if valid (e.g. USER@DOMAIN.COM -> user@domain.com).
    """

    STEP = 1
    NAME = "Syntax"

    def run(self, email: str) -> dict:
        try:
            result = validate_email(email, check_deliverability=False)
            normalized = result.normalized
            Logger.step(self.STEP, self.NAME, True, f"Valid format -> {normalized}")
            return {"passed": True, "email": normalized}
        except EmailNotValidError as e:
            Logger.step(self.STEP, self.NAME, False, str(e))
            return {"passed": False, "reason": f"invalid_syntax: {e}"}


# =============================================================================
# STEP 2 — STATIC BLOCKLIST
# =============================================================================

class StepStaticBlocklist:
    """
    Checks if the domain is in the +100k static blocklist loaded from GitHub.
    This is the fastest disposable domain check — no network call needed.
    """

    STEP = 2
    NAME = "Static blocklist"

    def __init__(self, blocklist: StaticBlocklist):
        self.blocklist = blocklist

    def run(self, domain: str) -> dict:
        if self.blocklist.contains(domain):
            Logger.step(self.STEP, self.NAME, False, f"{domain} found in blocklist (+100k domains)")
            return {"passed": False, "reason": "disposable_static_list"}

        Logger.step(self.STEP, self.NAME, True, f"{domain} not in static blocklist")
        return {"passed": True}


# =============================================================================
# STEP 3 — DNS / MX RECORDS
# =============================================================================

class StepDNS:
    """
    Resolves the MX records for the domain.
    If no MX records exist, the domain cannot receive emails.
    Also extracts the MX server hostname for use in Step 4.
    """

    STEP = 3
    NAME = "DNS / MX records"

    def run(self, domain: str) -> dict:
        try:
            mx_records = dns.resolver.resolve(domain, "MX", lifetime=Config.DNS_TIMEOUT)
            servers    = sorted([(r.preference, str(r.exchange).rstrip(".")) for r in mx_records])
            mx_server  = servers[0][1]
            Logger.step(self.STEP, self.NAME, True, f"MX found -> {mx_server}")
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


# =============================================================================
# STEP 4 — PROVIDER CHECK
# =============================================================================

class StepProvider:
    """
    Detects if the email is hosted on a trusted provider
    (Gmail, Outlook, Google Workspace, Zoho, Microsoft 365...).

    Detection uses two methods :
        A) Domain name   : gmail.com, outlook.com ...
        B) MX server     : aspmx.l.google.com -> Google Workspace
                           mail.protection.outlook.com -> Microsoft 365
                           mx.zoho.com -> Zoho Mail

    If detected -> accept immediately, Steps 5 & 6 are skipped entirely.
    If not      -> continue to Steps 5 & 6 for disposable detection.
    """

    STEP = 4
    NAME = "Provider check"

    def run(self, domain: str, mx_server: str) -> dict:
        mx_parts    = mx_server.split(".")
        mx_domain_2 = ".".join(mx_parts[-2:]) if len(mx_parts) >= 2 else mx_server
        mx_domain_3 = ".".join(mx_parts[-3:]) if len(mx_parts) >= 3 else mx_domain_2

        is_major = (
            domain      in Config.MAJOR_PROVIDERS      or
            mx_domain_2 in Config.TRUSTED_MX_PROVIDERS or
            mx_domain_3 in Config.TRUSTED_MX_PROVIDERS
        )

        if is_major:
            if domain in Config.MAJOR_PROVIDERS:
                label = f"{domain} is a major provider"
            else:
                label = f"hosted on {mx_server} (Google Workspace / Zoho / Microsoft 365)"
            Logger.step(self.STEP, self.NAME, True, f"{label} — trusted infrastructure")
            return {"passed": True, "is_major_provider": True}

        Logger.skip(self.STEP, self.NAME, f"{domain} is not a major provider (MX: {mx_server})")
        return {"passed": True, "is_major_provider": False}


# =============================================================================
# STEP 5 — DISIFY API
# =============================================================================

class StepDisify:
    """
    Calls the Disify API to check if the domain is disposable.
    Free, no signup, no API key required.
    Also checks if the domain has valid DNS according to Disify.

    Only reached when Step 4 does NOT detect a trusted provider.

    API docs : https://www.disify.com
    """

    STEP = 5
    NAME = "Disify API"

    def run(self, email: str) -> dict:
        try:
            response = requests.get(
                f"https://www.disify.com/api/email/{email}",
                timeout=Config.API_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            is_disposable = data.get("disposable", False)
            dns_valid     = data.get("dns", False)

            if is_disposable:
                Logger.step(self.STEP, self.NAME, False, "Flagged as disposable")
                return {"passed": False, "reason": "disposable_disify"}

            Logger.step(self.STEP, self.NAME, True, f"Not disposable (dns_valid={dns_valid})")
            return {"passed": True, "dns_valid": dns_valid}

        except requests.exceptions.Timeout:
            Logger.skip(self.STEP, self.NAME, "API timeout — continuing to Step 6")
            return {"passed": True, "skipped": True}

        except Exception as e:
            Logger.skip(self.STEP, self.NAME, f"API unavailable ({e}) — continuing to Step 6")
            return {"passed": True, "skipped": True}


# =============================================================================
# STEP 6 — KICKBOX API
# =============================================================================

class StepKickbox:
    """
    Calls the Kickbox API as a second opinion on disposable domains.
    Useful when Disify misses a domain (e.g. dependity.com).
    Free, no signup, no API key required.

    Only reached when Step 4 does NOT detect a trusted provider.

    API docs : https://open.kickbox.com
    """

    STEP = 6
    NAME = "Kickbox API"

    def run(self, domain: str) -> dict:
        try:
            response = requests.get(
                f"https://open.kickbox.com/v1/disposable/{domain}",
                timeout=Config.API_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            is_disposable = data.get("disposable", False)

            if is_disposable:
                Logger.step(self.STEP, self.NAME, False, "Flagged as disposable")
                return {"passed": False, "reason": "disposable_kickbox"}

            Logger.step(self.STEP, self.NAME, True, "Not disposable")
            return {"passed": True}

        except requests.exceptions.Timeout:
            Logger.skip(self.STEP, self.NAME, "API timeout — trusting MX")
            return {"passed": True, "skipped": True}

        except Exception as e:
            Logger.skip(self.STEP, self.NAME, f"API unavailable ({e}) — trusting MX")
            return {"passed": True, "skipped": True}


# =============================================================================
# EMAIL VERIFIER — orchestrates all 6 steps
# =============================================================================

class EmailVerifier:
    """
    Main class. Runs all 6 verification steps in order.
    Stops as soon as a step fails (early exit = fast).

    Major providers (Gmail, Outlook, Google Workspace, Zoho, M365) are
    accepted after Step 4 — Steps 5 & 6 are skipped entirely, saving
    two API round-trips per address.

    Usage :
        verifier = EmailVerifier()          # loads blocklist once
        result   = verifier.verify("x@y.com")
        ok       = verifier.check("x@y.com")  # returns bool directly
    """

    def __init__(self):
        blocklist        = StaticBlocklist()
        self.step_syntax = StepSyntax()
        self.step_list   = StepStaticBlocklist(blocklist)
        self.step_dns    = StepDNS()
        self.step_prov   = StepProvider()
        self.step_disify = StepDisify()
        self.step_kickbx = StepKickbox()

    # ── private helpers ────────────────────────────────────────────────────

    def _skip_from(self, from_step: int):
        """Logs all remaining steps as skipped."""
        steps = {
            2: "Static blocklist",
            3: "DNS / MX records",
            4: "Provider check",
            5: "Disify API",
            6: "Kickbox API",
        }
        for number, name in steps.items():
            if number >= from_step:
                Logger.skip(number, name, "skipped")

    def _reject(self, reason: str) -> dict:
        Logger.footer(False, reason)
        return {"valid": False, "reason": reason}

    def _accept(self, reason: str) -> dict:
        Logger.footer(True, reason)
        return {"valid": True, "reason": reason}

    # ── public interface ───────────────────────────────────────────────────

    def verify(self, email: str) -> dict:
        """
        Runs all steps and returns a result dict :
            { "valid": bool, "reason": str }
        """
        Logger.header(email)

        # Step 1 — Syntax
        s1 = self.step_syntax.run(email)
        if not s1["passed"]:
            self._skip_from(2)
            return self._reject(s1["reason"])

        email  = s1["email"]
        domain = email.split("@")[1]

        # Step 2 — Static blocklist
        s2 = self.step_list.run(domain)
        if not s2["passed"]:
            self._skip_from(3)
            return self._reject(s2["reason"])

        # Step 3 — DNS / MX
        s3 = self.step_dns.run(domain)
        if not s3["passed"]:
            self._skip_from(4)
            return self._reject(s3["reason"])

        mx_server = s3["mx_server"]

        # Step 4 — Provider check
        # ─────────────────────────────────────────────────────────────────
        # Major provider detected → trusted infrastructure, no API checks
        # needed. Skip Steps 5 & 6 entirely and accept immediately.
        # ─────────────────────────────────────────────────────────────────
        s4 = self.step_prov.run(domain, mx_server)
        if s4["is_major_provider"]:
            self._skip_from(5)
            return self._accept("major_provider_trusted")

        # Step 5 — Disify API  (only for unknown providers)
        s5 = self.step_disify.run(email)
        if not s5["passed"]:
            Logger.skip(6, "Kickbox API", "skipped — already rejected by Disify")
            return self._reject(s5["reason"])

        # Step 6 — Kickbox API  (only for unknown providers)
        s6 = self.step_kickbx.run(domain)
        if not s6["passed"]:
            return self._reject(s6["reason"])

        return self._accept("all_checks_passed")

    def check(self, email: str) -> bool:
        """
        Shorthand — returns True if the email is valid, False otherwise.
        Use this in your workflow.
        """
        return self.verify(email)["valid"]


# =============================================================================
# RUNNER — batch processing with summary
# =============================================================================

class EmailRunner:
    """
    Processes a list of emails and prints a summary.
    Plug your AI generation and Gmail sending inside the 'if valid' block.
    """

    def __init__(self):
        self.verifier = EmailVerifier()

    def run(self, emails: list):
        print(Logger.color("\n" + "═" * 65, "cyan"))
        print(Logger.color("  EMAIL VERIFICATION REPORT", "bold"))
        print(Logger.color("═" * 65, "cyan"))

        valid_count   = 0
        skipped_count = 0

        for email in emails:
            if self.verifier.check(email):
                valid_count += 1
                # ← YOUR CODE HERE :
                # message = generate_ai_message(email)
                # send_gmail(email, message)
            else:
                skipped_count += 1
                # ← Nothing — 0 AI tokens, 0 Gmail quota used

        Logger.summary(len(emails), valid_count, skipped_count)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    test_emails = [
        "utilisateur@gmail.com",            # valid   — major provider
        "quelquun@outlook.com",             # valid   — major provider
        "contact@python.org",               # valid   — professional domain
        "info@heuristik.tech",              # valid   — Google Workspace hosted
        "pasdarobase.com",                  # invalid — no @ sign
        "double@@domaine.com",              # invalid — bad syntax
        "test@domainequiexistepas123.xyz",  # invalid — domain doesn't exist
        "temp@mailinator.com",              # invalid — static blocklist
        "jetable@yopmail.com",              # invalid — static blocklist
        "lanetta54@dependity.com",          # invalid — caught by Kickbox
        "hello@takpay.com",                 # invalid — no MX records
    ]

    runner = EmailRunner()
    runner.run(test_emails)