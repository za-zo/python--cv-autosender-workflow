"""
=============================================================================
EMAIL VERIFIER  —  REINFORCED EDITION
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
    2. Static list     — domain checked against 3 merged GitHub blocklists :
                           • disposable-email-domains/disposable-email-domains  (~120k domains)
                           • disposable/disposable-email-domains                 (~60k  domains)
                           • ivolo/disposable-email-domains                      (~40k  domains)
                         Each source is fetched concurrently at startup and
                         merged into a single de-duplicated set.
    3. DNS / MX        — does the domain have a mail server ?
    4. Provider        — is it Gmail / Google Workspace / Zoho / Microsoft 365 ?
                         ↳ YES → accept immediately, skip Steps 5 & 6
    5. API checks      — 4 free keyless APIs called concurrently :
                           • Disify      https://www.disify.com
                           • Kickbox     https://open.kickbox.com
                           • DeBounce    https://disposable.debounce.io
                           • ValidatorPizza / UserCheck  https://www.validator.pizza
                         Any single "disposable" verdict → reject.
                         Skipped sources (timeout / unavailable) are ignored.
    6. Final verdict   — if all API checks pass → accept
=============================================================================
"""

import concurrent.futures
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
        name_s = Logger.color(f"{name:<26}", "white")
        detail = Logger.color(message, "green") if passed else Logger.color(message, "red")
        print(f"   {label} {icon}  {name_s} {detail}")

    @staticmethod
    def skip(number: int, name: str, reason: str):
        label  = Logger.color(f"[Step {number}]", "cyan")
        name_s = Logger.color(f"{name:<26}", "gray")
        reason = Logger.color(f"— {reason}", "gray")
        print(f"   {label} -  {name_s} {reason}")

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
    LIST_TIMEOUT = 10 # seconds to fetch each blocklist from GitHub

    # ── Three GitHub blocklist sources, fetched concurrently at startup ───
    #
    #   SOURCE A  disposable-email-domains/disposable-email-domains
    #             Community-maintained since 2014, screenshot-verified additions.
    #             ~120 000 domains. One domain per line, plain text.
    #
    #   SOURCE B  disposable/disposable-email-domains
    #             Auto-generated daily from ~20 scraped providers.
    #             ~60 000 domains. Use domains.txt (not strict) for full coverage.
    #
    #   SOURCE C  ivolo/disposable-email-domains
    #             Raw JSON array — the list that powers the Kickbox API itself.
    #             ~40 000 domains. Good catch for domains Kickbox already knows.
    #
    BLOCKLIST_SOURCES = [
        {
            "name": "disposable-email-domains (community)",
            "url" : (
                "https://raw.githubusercontent.com/"
                "disposable-email-domains/disposable-email-domains/"
                "master/disposable_email_blocklist.conf"
            ),
            "format": "txt",   # one domain per line
        },
        {
            "name": "disposable/disposable-email-domains (daily auto)",
            "url" : (
                "https://raw.githubusercontent.com/"
                "disposable/disposable-email-domains/"
                "master/domains.txt"
            ),
            "format": "txt",
        },
        {
            "name": "ivolo/disposable-email-domains (Kickbox source)",
            "url" : (
                "https://raw.githubusercontent.com/"
                "ivolo/disposable-email-domains/"
                "master/index.json"
            ),
            "format": "json",  # JSON array of strings
        },
    ]

    # Fallback used only when ALL three GitHub sources are unreachable
    FALLBACK_BLOCKLIST = {
        "mailinator.com", "guerrillamail.com", "temp-mail.org", "yopmail.com",
        "trashmail.com", "fakeinbox.com", "10minutemail.com", "maildrop.cc",
        "throwaway.email", "discard.email", "spamgourmet.com", "tempr.email",
        "mohmal.com", "tempinbox.com", "dispostable.com", "sharklasers.com",
        "dependity.com", "emailondeck.com", "drrieca.com", "hostelness.com",
    }

    # Domains where SMTP verification is unreliable (they accept-all then filter)
    MAJOR_PROVIDERS = {
        "gmail.com", "googlemail.com",
        "outlook.com", "hotmail.com", "live.com", "msn.com",
        "yahoo.com", "yahoo.fr", "yahoo.co.uk",
        "icloud.com", "me.com", "mac.com",
        "aol.com", "protonmail.com", "proton.me",
    }

    # MX server base-domains that indicate trusted hosting infrastructure
    TRUSTED_MX_PROVIDERS = {
        "google.com",              # Google Workspace  -> aspmx.l.google.com
        "googlemail.com",          # Google Workspace  -> alt*.aspmx.l.google.com
        "outlook.com",             # Microsoft 365     -> *.mail.protection.outlook.com
        "protection.outlook.com",  # Microsoft 365
        "yahoodns.net",            # Yahoo Business
        "zoho.com",                # Zoho Mail         -> mx.zoho.com
        "zoho.in",                 # Zoho Mail India
        "zoho.eu",                 # Zoho Mail Europe
        "mimecast.com",            # Mimecast (enterprise filter)
        "pphosted.com",            # Proofpoint (enterprise filter)
    }


# =============================================================================
# STATIC BLOCKLIST — three GitHub sources merged at startup
# =============================================================================

class StaticBlocklist:
    """
    Downloads and merges three independent GitHub blocklists concurrently.

    Sources are fetched in parallel with ThreadPoolExecutor so startup time
    equals the slowest single request, not the sum of all three.

    The resulting set is de-duplicated automatically by Python's set union.
    If a source is unavailable its contribution is silently skipped; the
    fallback hard-coded set is only used when ALL sources fail.
    """

    def __init__(self):
        self.domains = self._load()

    # ── private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _fetch_source(source: dict) -> set:
        """Fetch and parse a single blocklist source. Returns a set of domains."""
        try:
            response = requests.get(source["url"], timeout=Config.LIST_TIMEOUT)
            response.raise_for_status()

            if source["format"] == "json":
                import json
                raw = json.loads(response.text)
                domains = {d.strip().lower() for d in raw if isinstance(d, str) and d.strip()}
            else:
                domains = {
                    line.strip().lower()
                    for line in response.text.splitlines()
                    if line.strip() and not line.startswith("#")
                }

            print(f"[INIT] ✓ {len(domains):>7} domains  ← {source['name']}")
            return domains

        except Exception as e:
            print(f"[INIT] ✗ Skipped (error: {e})  ← {source['name']}")
            return set()

    def _load(self) -> set:
        print("[INIT] Loading blocklists concurrently from 3 GitHub sources …")
        merged: set = set()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(self._fetch_source, src): src
                for src in Config.BLOCKLIST_SOURCES
            }
            for future in concurrent.futures.as_completed(futures):
                merged |= future.result()

        if merged:
            print(f"[INIT] ✅ {len(merged):>7} unique disposable domains loaded (3 sources merged)")
            return merged

        # All three sources failed — use the embedded fallback
        print(f"[INIT] ⚠️  All GitHub sources unreachable → using built-in fallback list")
        return Config.FALLBACK_BLOCKLIST

    def contains(self, domain: str) -> bool:
        return domain.lower() in self.domains


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
            result     = validate_email(email, check_deliverability=False)
            normalized = result.normalized
            Logger.step(self.STEP, self.NAME, True, f"Valid format → {normalized}")
            return {"passed": True, "email": normalized}
        except EmailNotValidError as e:
            Logger.step(self.STEP, self.NAME, False, str(e))
            return {"passed": False, "reason": f"invalid_syntax: {e}"}


# =============================================================================
# STEP 2 — STATIC BLOCKLIST  (3 sources merged)
# =============================================================================

class StepStaticBlocklist:
    """
    Checks the domain against the merged 3-source static blocklist.
    This is the fastest disposable check — pure in-memory set lookup, O(1).
    """

    STEP = 2
    NAME = "Static blocklist (×3)"

    def __init__(self, blocklist: StaticBlocklist):
        self.blocklist = blocklist

    def run(self, domain: str) -> dict:
        if self.blocklist.contains(domain):
            Logger.step(self.STEP, self.NAME, False,
                        f"{domain} found in merged blocklist")
            return {"passed": False, "reason": "disposable_static_list"}

        Logger.step(self.STEP, self.NAME, True,
                    f"{domain} not in merged blocklist ({len(self.blocklist.domains):,} entries)")
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


# =============================================================================
# STEP 4 — PROVIDER CHECK
# =============================================================================

class StepProvider:
    """
    Detects if the email is hosted on a trusted provider
    (Gmail, Outlook, Google Workspace, Zoho, Microsoft 365...).

    Detection uses two methods :
        A) Domain name   : gmail.com, outlook.com ...
        B) MX server     : aspmx.l.google.com       → Google Workspace
                           mail.protection.outlook.com → Microsoft 365
                           mx.zoho.com               → Zoho Mail

    If detected → accept immediately, Step 5 is skipped entirely.
    If not      → continue to Step 5 for the API disposable checks.
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
                label = f"hosted on {mx_server} (Google WS / Zoho / M365)"
            Logger.step(self.STEP, self.NAME, True, f"{label} — trusted infrastructure")
            return {"passed": True, "is_major_provider": True}

        Logger.skip(self.STEP, self.NAME,
                    f"{domain} is not a major provider (MX: {mx_server})")
        return {"passed": True, "is_major_provider": False}


# =============================================================================
# STEP 5 — FOUR FREE KEYLESS APIS  (run concurrently)
# =============================================================================

# ── Individual API callers ─────────────────────────────────────────────────

def _call_disify(email: str) -> dict:
    """
    Disify API — free, no key required.
    https://www.disify.com/api/email/{email}
    Returns {"disposable": bool, "dns": bool, ...}
    """
    try:
        r = requests.get(
            f"https://www.disify.com/api/email/{email}",
            timeout=Config.API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return {
            "api"        : "Disify",
            "disposable" : bool(data.get("disposable", False)),
            "available"  : True,
        }
    except Exception as e:
        return {"api": "Disify", "available": False, "error": str(e)}


def _call_kickbox(domain: str) -> dict:
    """
    Kickbox Open API — free, no key required.
    https://open.kickbox.com/v1/disposable/{domain}
    Returns {"disposable": bool}
    """
    try:
        r = requests.get(
            f"https://open.kickbox.com/v1/disposable/{domain}",
            timeout=Config.API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return {
            "api"        : "Kickbox",
            "disposable" : bool(data.get("disposable", False)),
            "available"  : True,
        }
    except Exception as e:
        return {"api": "Kickbox", "available": False, "error": str(e)}


def _call_debounce(email: str) -> dict:
    """
    DeBounce Free Disposable API — free, no key required, CORS enabled.
    https://disposable.debounce.io/?email={email}
    Returns {"disposable": "true"|"false"}

    DeBounce maintains their own continuously-updated domain list —
    a different dataset from Disify and Kickbox, which improves coverage.
    """
    try:
        r = requests.get(
            f"https://disposable.debounce.io/?email={email}",
            timeout=Config.API_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        # API returns the string "true" or "false", not a bool
        raw          = data.get("disposable", "false")
        is_disposable = str(raw).lower() == "true"
        return {
            "api"        : "DeBounce",
            "disposable" : is_disposable,
            "available"  : True,
        }
    except Exception as e:
        return {"api": "DeBounce", "available": False, "error": str(e)}


def _call_validator_pizza(domain: str) -> dict:
    """
    Validator.pizza (now rebranded as UserCheck) — free, no key required.
    https://www.validator.pizza/domain/{domain}
    Returns {"status": int, "mx": bool, "disposable": bool, ...}

    Rate-limited to 120 requests/hour on the free tier.
    Checks a different internal list; good at catching alias / relay domains.
    On rate-limit (HTTP 429) or any error the result is treated as "unknown"
    and the check is skipped rather than blocking the address.
    """
    try:
        r = requests.get(
            f"https://www.validator.pizza/domain/{domain}",
            timeout=Config.API_TIMEOUT
        )
        if r.status_code == 429:
            return {"api": "ValidatorPizza", "available": False,
                    "error": "rate limit reached (120 req/h)"}
        r.raise_for_status()
        data = r.json()
        return {
            "api"        : "ValidatorPizza",
            "disposable" : bool(data.get("disposable", False)),
            "available"  : True,
        }
    except Exception as e:
        return {"api": "ValidatorPizza", "available": False, "error": str(e)}


# ── Step orchestrator ─────────────────────────────────────────────────────

class StepApiChecks:
    """
    Runs all four free keyless APIs concurrently using ThreadPoolExecutor.

    Total wait time = max(individual timeouts) instead of their sum.
    A single "disposable: True" from ANY available API triggers rejection.
    Unavailable / timed-out APIs are logged as skipped and do not block.

    APIs used (all free, no registration, no API key):
        • Disify          https://www.disify.com
        • Kickbox         https://open.kickbox.com
        • DeBounce        https://disposable.debounce.io
        • ValidatorPizza  https://www.validator.pizza
    """

    STEP = 5
    NAME = "API checks (×4, async)"

    def run(self, email: str, domain: str) -> dict:
        # Launch all four API calls in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_call_disify,          email ): "Disify",
                pool.submit(_call_kickbox,          domain): "Kickbox",
                pool.submit(_call_debounce,         email ): "DeBounce",
                pool.submit(_call_validator_pizza,  domain): "ValidatorPizza",
            }
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Evaluate results — any positive disposable verdict rejects the address
        reject_reason = None
        lines         = []

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

        # Check if we have at least one available result; if all APIs were
        # unavailable we still pass (fail-open) so a network hiccup doesn't
        # silently block every legitimate address.
        available_count = sum(1 for r in results if r["available"])
        if available_count == 0:
            Logger.step(self.STEP, self.NAME, True,
                        "all APIs unavailable — trusting MX records")
        else:
            Logger.step(self.STEP, self.NAME, True,
                        f"not disposable ({available_count}/4 APIs responded)")
        print("\n".join(lines))
        return {"passed": True}


# =============================================================================
# EMAIL VERIFIER — orchestrates all steps
# =============================================================================

class EmailVerifier:
    """
    Main class. Runs all verification steps in order.
    Stops as soon as a step fails (early exit = fast).

    Flow:
        Step 1  Syntax check
        Step 2  Merged static blocklist (3 sources, ~150k+ domains)
        Step 3  DNS / MX records
        Step 4  Trusted provider detection → early accept if matched
        Step 5  Four free keyless APIs run concurrently

    Usage:
        verifier = EmailVerifier()          # loads blocklists once
        result   = verifier.verify("x@y.com")
        ok       = verifier.check("x@y.com")  # returns bool directly
    """

    def __init__(self):
        blocklist        = StaticBlocklist()
        self.step_syntax = StepSyntax()
        self.step_list   = StepStaticBlocklist(blocklist)
        self.step_dns    = StepDNS()
        self.step_prov   = StepProvider()
        self.step_apis   = StepApiChecks()

    # ── private helpers ────────────────────────────────────────────────────

    def _skip_from(self, from_step: int):
        steps = {
            2: ("Static blocklist (×3)",   StepStaticBlocklist),
            3: ("DNS / MX records",         StepDNS),
            4: ("Provider check",           StepProvider),
            5: ("API checks (×4, async)",   StepApiChecks),
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

    # ── public interface ───────────────────────────────────────────────────

    def verify(self, email: str) -> dict:
        """
        Runs all steps and returns a result dict:
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

        # Step 2 — Merged static blocklist
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
        # Trusted infrastructure detected → accept immediately.
        # Step 5 (API checks) is skipped entirely — saves 4 API round-trips.
        # ─────────────────────────────────────────────────────────────────
        s4 = self.step_prov.run(domain, mx_server)
        if s4["is_major_provider"]:
            Logger.skip(5, "API checks (×4, async)", "skipped — major provider trusted")
            return self._accept("major_provider_trusted")

        # Step 5 — Four free APIs run concurrently
        s5 = self.step_apis.run(email, domain)
        if not s5["passed"]:
            return self._reject(s5["reason"])

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
        "contact@saastrail.com",
        "info@cloudeasy.io",
        "hola@dosmedia.es",
        "amine.belkeziz@upline.co.ma",
        "nachrane@krafteurope.com",
        "careers@gft.com",
        "alachkar@atento.ma",
        "bouchaib.nassef@oilibya.ma",
        "benhammou@mail.cbi.net.ma",
    ]

    runner = EmailRunner()
    runner.run(test_emails)