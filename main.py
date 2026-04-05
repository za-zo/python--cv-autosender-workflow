import base64
import signal
import sys
import tempfile
import time

import requests

import config
from ai import get_provider_module
from ai.base import (
    build_cv_prompt,
    build_message_prompt,
    parse_cv_response,
    parse_message_response,
)
from db import ai_api_keys, companies, emails, jobs, profiles, providers
from helpers.email_sender import send_email
from helpers.html_cv import generate_html_cv
from helpers.notification_body import (
    build_context_html,
    format_smtp_line,
    format_updates_html,
)


def mask(val, kind="str"):
    """Mask sensitive values when config.MASK_LOGS is enabled."""
    if not config.MASK_LOGS:
        return val
    s = str(val) if val else ""
    if not s:
        return ""
    if kind == "email":
        return "***@***.***"
    if kind == "secret":
        return "********"
    if kind == "json":
        return "[MASKED]"
    return "***"


def _html_escape(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_current_job_id = None
_claimed_email_id = None
_claimed_cv_api_key_id = None
_claimed_msg_api_key_id = None


def _reset_claimed_ids():
    global _claimed_email_id, _claimed_cv_api_key_id, _claimed_msg_api_key_id
    _claimed_email_id = None
    _claimed_cv_api_key_id = None
    _claimed_msg_api_key_id = None


def _release_claimed_resources():
    global _claimed_email_id, _claimed_cv_api_key_id, _claimed_msg_api_key_id
    if _claimed_msg_api_key_id:
        print(f"  -> Releasing message API key {mask(_claimed_msg_api_key_id)}...")
        try:
            ai_api_keys.release_api_key_in_use(_claimed_msg_api_key_id)
            print(f"  -> Message API key released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release message API key: {mask(str(e))}")
        _claimed_msg_api_key_id = None
    if _claimed_cv_api_key_id:
        print(f"  -> Releasing CV API key {mask(_claimed_cv_api_key_id)}...")
        try:
            ai_api_keys.release_api_key_in_use(_claimed_cv_api_key_id)
            print(f"  -> CV API key released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release CV API key: {mask(str(e))}")
        _claimed_cv_api_key_id = None
    if _claimed_email_id:
        print(f"  -> Releasing email {mask(_claimed_email_id)}...")
        try:
            emails.release_email_in_use(_claimed_email_id)
            print(f"  -> Email released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release email: {mask(str(e))}")
        _claimed_email_id = None


def _smtp_pair(smtp_email, smtp_password):
    if smtp_email and smtp_password:
        return smtp_email, smtp_password
    ne, np = config.NOTIFICATION_SMTP_EMAIL, config.NOTIFICATION_SMTP_PASSWORD
    if ne and np:
        return ne, np
    return None, None


def _notify_kw(
    smtp_email=None,
    smtp_password=None,
    email_config=None,
    cv_api_key=None,
    msg_api_key=None,
    cv_provider=None,
    msg_provider=None,
    company=None,
):
    """Keyword args for fail_and_notify from current workflow state."""
    return {
        "smtp_email": smtp_email,
        "smtp_password": smtp_password,
        "email_config": email_config,
        "cv_api_key": cv_api_key,
        "msg_api_key": msg_api_key,
        "cv_provider": cv_provider,
        "msg_provider": msg_provider,
        "company": company,
    }


def _handle_exit(signum, frame):
    """Release claimed job and pool resources on interrupt/terminate, then exit."""
    sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM" if signum == signal.SIGTERM else f"signal {signum}"
    print(f"\n  -> Received {sig_name}, initiating cleanup...")
    if _current_job_id:
        print(f"  -> Releasing job {mask(_current_job_id)}...")
        try:
            jobs.release_job(_current_job_id)
            print(f"  -> Job released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release job: {mask(str(e))}")
    _release_claimed_resources()
    print("  -> Exited.")
    sys.exit(1)


def fail_and_notify(
    job,
    reason,
    *,
    api_key_to_deactivate=None,
    api_key_deactivate_desc="API key",
    email_to_deactivate=None,
    smtp_email=None,
    smtp_password=None,
    company=None,
    cv_provider=None,
    msg_provider=None,
    cv_api_key=None,
    msg_api_key=None,
    email_config=None,
    updates_made=None,
):
    """Mark job as failed, optionally deactivate API key/email, send error email."""
    job_id = str(job["_id"])
    updates = list(updates_made) if updates_made else []

    if api_key_to_deactivate:
        print(f"  -> Deactivating API key {mask(api_key_deactivate_desc)}...")
        try:
            ai_api_keys.deactivate_api_key(str(api_key_to_deactivate["_id"]))
            updates.append(
                f"{api_key_deactivate_desc} was deactivated (active=false, in_use=false)."
            )
            print(f"  -> API key deactivated.")
        except Exception as e:
            print(f"  -> [WARN] Failed to deactivate API key: {mask(str(e))}")

    if email_to_deactivate:
        print(f"  -> Deactivating email account...")
        try:
            emails.deactivate_email(str(email_to_deactivate["_id"]))
            updates.append("Email account was deactivated (active=false, in_use=false).")
            print(f"  -> Email account deactivated.")
        except Exception as e:
            print(f"  -> [WARN] Failed to deactivate email: {mask(str(e))}")

    print(f"  -> Marking job as failed...")
    try:
        jobs.mark_failed(job_id, reason)
        updates.append("Job was updated: status=failed, active=false, in_use=false.")
        print(f"  -> Job marked as failed.")
    except Exception as e:
        print(f"  -> [WARN] Failed to mark job as failed: {mask(str(e))}")

    pair_e, pair_p = _smtp_pair(smtp_email, smtp_password)
    try:
        ctx = build_context_html(
            job,
            company=company,
            cv_provider=cv_provider,
            msg_provider=msg_provider,
            cv_api_key=cv_api_key,
            msg_api_key=msg_api_key,
            email_config=email_config,
        )
        body = (
            f"<h2>❌ Job Failed</h2>"
            f"<p><strong>Reason:</strong> {_html_escape(reason)}</p>"
            f"<hr/>"
            f"{ctx}"
            f"{format_updates_html(updates)}"
        )
        subj = "❌ Job Failed — " + reason.replace("\n", " ").strip()[:200]
        if pair_e and pair_p and config.NOTIFICATION_EMAIL:
            send_email(
                config.NOTIFICATION_EMAIL,
                subj,
                body,
                pair_e,
                pair_p,
            )
        else:
            print("  -> [WARN] No SMTP credentials or NOTIFICATION_EMAIL, skipping failure notification email.")
    except Exception:
        pass

    print(f"  -> [FAIL] {mask(reason)}")
    exit(1)


def _fail_email_claim(job, raw_email_id):
    try:
        if raw_email_id:
            doc = emails.get_email_by_id(raw_email_id)
            if not doc:
                reason = "Email config not found (no document for this ID)"
            elif not doc.get("active", False):
                reason = "Email config is INACTIVE (not available for claiming)"
            elif doc.get("in_use"):
                reason = "Email config is already IN USE by another worker"
            else:
                reason = "Email could not be claimed (unexpected state)"
            fail_and_notify(job, reason, email_config=doc if doc else None)
        else:
            fail_and_notify(
                job,
                "No available email in pool (need active=true and not in_use)",
            )
    except SystemExit:
        raise
    except Exception as e:
        fail_and_notify(
            job,
            f"[Step 02] Email claim failure handling — {e}",
        )


def _fail_cv_key_claim(job, raw_key_id, email_config, smtp_email, smtp_password):
    try:
        if raw_key_id:
            doc = ai_api_keys.get_api_key_by_id(raw_key_id)
            if not doc:
                reason = "CV API key not found (no document for this ID)"
            elif not doc.get("active", False):
                reason = "CV API key is INACTIVE (not available for claiming)"
            elif doc.get("in_use"):
                reason = "CV API key is already IN USE by another worker"
            else:
                reason = "CV API key could not be claimed (unexpected state)"
            fail_and_notify(
                job,
                reason,
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
                cv_api_key=doc if doc else None,
            )
        else:
            fail_and_notify(
                job,
                "No available CV API key in pool (need active=true and not in_use)",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
            )
    except SystemExit:
        raise
    except Exception as e:
        fail_and_notify(
            job,
            f"[Step 03] CV API key claim failure handling — {e}",
            **_notify_kw(
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
            ),
        )


def _fail_msg_key_claim(job, raw_key_id, email_config, smtp_email, smtp_password, cv_api_key):
    try:
        if raw_key_id:
            doc = ai_api_keys.get_api_key_by_id(raw_key_id)
            if not doc:
                reason = "Message API key not found (no document for this ID)"
            elif not doc.get("active", False):
                reason = "Message API key is INACTIVE (not available for claiming)"
            elif doc.get("in_use"):
                reason = "Message API key is already IN USE by another worker"
            else:
                reason = "Message API key could not be claimed (unexpected state)"
            fail_and_notify(
                job,
                reason,
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
                cv_api_key=cv_api_key,
                msg_api_key=doc if doc else None,
            )
        else:
            fail_and_notify(
                job,
                "No available message API key in pool (need active=true and not in_use)",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
                cv_api_key=cv_api_key,
            )
    except SystemExit:
        raise
    except Exception as e:
        fail_and_notify(
            job,
            f"[Step 04] Message API key claim failure handling — {e}",
            **_notify_kw(
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
                cv_api_key=cv_api_key,
            ),
        )


def call_ai_with_retries(provider_module, api_key, system_msg, user_msg, model_name=None):
    """Call AI provider with retry logic."""
    last_error = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return provider_module.call(api_key, system_msg, user_msg, model_name=model_name)
        except Exception as e:
            last_error = e
            if attempt < config.MAX_RETRIES:
                print(f"  -> Retry {attempt}/{config.MAX_RETRIES} failed, waiting {config.RETRY_WAIT_SECONDS}s...")
                time.sleep(config.RETRY_WAIT_SECONDS)
    raise last_error


def main():
    global _current_job_id, _claimed_email_id, _claimed_cv_api_key_id, _claimed_msg_api_key_id
    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)

    print("[Step 01] Claiming a job...")
    try:
        job = jobs.claim_job()
    except Exception as e:
        print(f"  -> [Step 01] Claim job failed: {mask(str(e))}")
        print("---------------")
        return
    if not job:
        print("  -> No active job found. Exiting.")
        print("---------------")
        return

    job_target_position = str(job.get("targetPosition", ""))
    job_id = str(job["_id"])
    _current_job_id = job_id
    _reset_claimed_ids()
    print(f"  -> Job claimed: {mask(job_target_position)} | ID: {mask(job_id)} | Company ID: {mask(job.get('companyId', ''))}")

    smtp_email = smtp_password = None
    email_config = None
    cv_api_key = msg_api_key = None
    cv_provider = msg_provider = None
    company = profile = None

    try:
        print("  ")
        print("[Step 02] Reading company...")
        try:
            company = companies.get_company(job["companyId"])
            if company:
                print(f"  -> Company loaded: {mask(company.get('name', ''))} | {mask(company.get('email', ''), 'email')}")
            else:
                print(f"  -> [WARN] Company not found for ID: {mask(job.get('companyId', ''))}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 02] Reading company — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    msg_provider=msg_provider,
                    company=company,
                ),
            )
        if not company:
            fail_and_notify(
                job,
                "[Step 02] Company not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    company=None,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    msg_provider=msg_provider,
                ),
            )

        print("  ")
        print("[Step 03] Claiming email config...")
        try:
            raw_email_id = job.get("emailId")
            print(f"  -> Looking for email (requested ID: {mask(raw_email_id) if raw_email_id else 'any available'})...")
            if raw_email_id:
                email_config = emails.claim_email_by_id(raw_email_id)
            else:
                email_config = emails.claim_available_email()
            if not email_config:
                print(f"  -> [WARN] Failed to claim email config")
                _fail_email_claim(job, raw_email_id)
            _claimed_email_id = str(email_config["_id"])
            smtp_email = email_config["smtp_email"]
            smtp_password = email_config["smtp_password"]
            print(f"  -> Email claimed: {mask(smtp_email, 'email')} | ID: {mask(_claimed_email_id)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 03] Claiming email config — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    company=company,
                ),
            )
        print(f"  -> Email: {mask(smtp_email, 'email')} | {mask(smtp_password, 'secret')}")

        print("  ")
        print("[Step 04] Claiming CV API key...")
        try:
            raw_cv_id = job.get("ai_api_key_id_for_cv_gen")
            print(f"  -> Looking for CV API key (requested ID: {mask(raw_cv_id) if raw_cv_id else 'any available'})...")
            if raw_cv_id:
                cv_api_key = ai_api_keys.claim_api_key_by_id(raw_cv_id)
            else:
                cv_api_key = ai_api_keys.claim_available_api_key()
            if not cv_api_key:
                print(f"  -> [WARN] Failed to claim CV API key")
                _fail_cv_key_claim(job, raw_cv_id, email_config, smtp_email, smtp_password)
            _claimed_cv_api_key_id = str(cv_api_key["_id"])
            print(f"  -> CV API key claimed: {mask(cv_api_key.get('name', ''))} | ID: {mask(_claimed_cv_api_key_id)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 04] Claiming CV API key — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    company=company,
                ),
            )
        print(
            f"  -> Key: {mask(cv_api_key.get('name', ''))} | "
            f"{mask(cv_api_key.get('apiKey', ''), 'secret')} | usage: {cv_api_key.get('usageCount', 0)}"
        )

        print("  ")
        print("[Step 05] Claiming message API key...")
        try:
            raw_msg_id = job.get("ai_api_key_id_for_message_gen")
            same_key_as_cv = raw_msg_id and raw_cv_id and str(raw_msg_id) == str(raw_cv_id)
            print(f"  -> Looking for message API key (requested ID: {mask(raw_msg_id) if raw_msg_id else 'any available'}, same as CV: {same_key_as_cv})...")
            if same_key_as_cv:
                msg_api_key = cv_api_key
                print(f"  -> Using same key as CV generation")
            elif raw_msg_id:
                msg_api_key = ai_api_keys.claim_api_key_by_id(raw_msg_id)
            else:
                msg_api_key = ai_api_keys.claim_available_api_key()
            if not msg_api_key:
                print(f"  -> [WARN] Failed to claim message API key")
                _fail_msg_key_claim(
                    job, raw_msg_id, email_config, smtp_email, smtp_password, cv_api_key
                )
            if not same_key_as_cv:
                _claimed_msg_api_key_id = str(msg_api_key["_id"])
                print(f"  -> Message API key claimed: {mask(msg_api_key.get('name', ''))} | ID: {mask(_claimed_msg_api_key_id)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 05] Claiming message API key — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    company=company,
                ),
            )
        msg_key_stats_id = _claimed_msg_api_key_id or _claimed_cv_api_key_id
        print(
            f"  -> Key: {mask(msg_api_key.get('name', ''))} | "
            f"{mask(msg_api_key.get('apiKey', ''), 'secret')} | usage: {msg_api_key.get('usageCount', 0)}"
        )

        print("  ")
        print("[Step 06] Reading CV API key provider...")
        try:
            cv_provider = providers.get_provider(cv_api_key["provider"])
            if cv_provider:
                print(f"  -> Provider: {mask(cv_provider.get('name', ''))}")
            else:
                print(f"  -> [WARN] Provider not found for ID: {mask(cv_api_key.get('provider', ''))}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 06] Reading CV API key provider — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    company=company,
                ),
            )
        if not cv_provider:
            fail_and_notify(
                job,
                "[Step 06] CV API key provider not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    company=company,
                ),
            )

        print("  ")
        print("[Step 07] Reading message API key provider...")
        try:
            msg_provider = providers.get_provider(msg_api_key["provider"])
            if msg_provider:
                print(f"  -> Provider: {mask(msg_provider.get('name', ''))}")
            else:
                print(f"  -> [WARN] Provider not found for ID: {mask(msg_api_key.get('provider', ''))}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 07] Reading message API key provider — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    company=company,
                ),
            )
        if not msg_provider:
            fail_and_notify(
                job,
                "[Step 07] Message API key provider not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    company=company,
                ),
            )

        print("  ")
        print("[Step 08] Reading profile...")
        try:
            profile = profiles.get_profile()
            if profile:
                print(f"  -> Profile loaded: {mask(profile.get('firstName', ''))} {mask(profile.get('lastName', ''))}")
            else:
                print(f"  -> [WARN] Profile not found")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 08] Reading profile — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    msg_provider=msg_provider,
                    company=company,
                ),
            )
        if not profile:
            fail_and_notify(
                job,
                "[Step 08] Profile not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    msg_provider=msg_provider,
                    company=company,
                ),
            )

        kw = _notify_kw(
            smtp_email=smtp_email,
            smtp_password=smtp_password,
            email_config=email_config,
            cv_api_key=cv_api_key,
            msg_api_key=msg_api_key,
            cv_provider=cv_provider,
            msg_provider=msg_provider,
            company=company,
        )

        print("  ")
        print("[Step 09] Building CV prompt...")
        try:
            cv_system_msg, cv_user_msg = build_cv_prompt(profile, company, job)
            print(f"  -> System prompt: {len(cv_system_msg)} chars, User prompt: {len(cv_user_msg)} chars")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 09] Building CV prompt — {e}", **kw)
        print(f"  -> OK (prompt: {len(cv_user_msg)} chars)")

        print("  ")
        print(f"[Step 10] Generating CV via {mask(cv_provider['name'])}...")
        try:
            cv_provider_module = get_provider_module(cv_provider["name"])
            print(f"  -> Provider module loaded: {mask(cv_provider['name'])}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 10] Loading CV provider module — {e}", **kw)
        try:
            print(f"  -> Calling AI with model: {mask(cv_provider.get('model_name', 'default'))}...")
            cv_raw_response = call_ai_with_retries(
                cv_provider_module,
                cv_api_key["apiKey"],
                cv_system_msg,
                cv_user_msg,
                model_name=cv_provider.get("model_name"),
            )
            print(f"  -> AI response received: {len(cv_raw_response)} chars")
        except SystemExit:
            raise
        except Exception as e:
            try:
                ai_api_keys.increment_api_key_stats(_claimed_cv_api_key_id, "failed")
            except SystemExit:
                raise
            except Exception as inc_e:
                fail_and_notify(
                    job,
                    f"[Step 10] CV API key stats after failed generation — {inc_e}",
                    **kw,
                )
            fail_and_notify(
                job,
                f"[Step 10] CV generation AI API error: {cv_provider['name']} — {e}",
                api_key_to_deactivate=cv_api_key,
                api_key_deactivate_desc="CV generation API key",
                **kw,
            )
        try:
            ai_api_keys.increment_api_key_stats(_claimed_cv_api_key_id, "success")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 10] CV API key usage stats after success — {e}", **kw)

        print("  ")
        print("[Step 11] Parsing CV response...")
        try:
            cv_data = parse_cv_response(cv_provider["name"], cv_raw_response)
            skills = cv_data.get("skills", [])
            print(f"  -> OK (skills: {len(skills)}, projects: {len(cv_data.get('projects', []))})")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 11] Parsing CV response (invalid or unexpected format) — {e}",
                **kw,
            )

        print("  ")
        print("[Step 12] Generating HTML CV...")
        try:
            html_content = generate_html_cv(cv_data, profile, job)
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 12] Generating HTML CV — {e}", **kw)
        print(f"  -> OK ({len(html_content)} chars)")

        print("  ")
        print("[Step 13] Building message prompt...")
        try:
            msg_system_msg, msg_user_msg, msg_lang = build_message_prompt(
                profile, company, job
            )
            print(f"  -> System prompt: {len(msg_system_msg)} chars, User prompt: {len(msg_user_msg)} chars, Language: {mask(msg_lang)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 13] Building message prompt — {e}", **kw)
        print(f"  -> OK (lang: {mask(msg_lang)}, prompt: {len(msg_user_msg)} chars)")

        print("  ")
        print(f"[Step 14] Generating message via {mask(msg_provider['name'])}...")
        try:
            msg_provider_module = get_provider_module(msg_provider["name"])
            print(f"  -> Provider module loaded: {mask(msg_provider['name'])}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 14] Loading message provider module — {e}", **kw)
        try:
            print(f"  -> Calling AI with model: {mask(msg_provider.get('model_name', 'default'))}...")
            msg_raw_response = call_ai_with_retries(
                msg_provider_module,
                msg_api_key["apiKey"],
                msg_system_msg,
                msg_user_msg,
                model_name=msg_provider.get("model_name"),
            )
            print(f"  -> AI response received: {len(msg_raw_response)} chars")
        except SystemExit:
            raise
        except Exception as e:
            try:
                ai_api_keys.increment_api_key_stats(msg_key_stats_id, "failed")
            except SystemExit:
                raise
            except Exception as inc_e:
                fail_and_notify(
                    job,
                    f"[Step 14] Message API key stats after failed generation — {inc_e}",
                    **kw,
                )
            fail_and_notify(
                job,
                f"[Step 14] Message generation AI API error: {msg_provider['name']} — {e}",
                api_key_to_deactivate=msg_api_key,
                api_key_deactivate_desc="Message generation API key",
                **kw,
            )
        try:
            ai_api_keys.increment_api_key_stats(msg_key_stats_id, "success")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 14] Message API key usage stats after success — {e}", **kw)

        print("  ")
        print("[Step 15] Parsing message response...")
        try:
            message_text = parse_message_response(msg_provider["name"], msg_raw_response)
            print(f"  -> OK ({len(message_text)} chars)")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 15] Parsing message response — {e}",
                **kw,
            )

        print("  ")
        print("[Step 16] Converting HTML to PDF...")
        print(f"  -> HTML content size: {len(html_content)} chars")
        pdf_base64 = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            print(f"  -> Attempt {attempt}/{config.MAX_RETRIES} to HTML2PDF service...")
            try:
                resp = requests.post(
                    config.HTML2PDF_URL,
                    json={
                        "html": html_content,
                        "format": "A4",
                        "orientation": "portrait",
                        "printBackground": True,
                        "margin": {
                            "top": "10mm",
                            "bottom": "10mm",
                            "left": "10mm",
                            "right": "10mm",
                        },
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                pdf_base64 = resp.json().get("pdf")
                if not pdf_base64:
                    raise ValueError("No PDF in response")
                print(f"  -> PDF generated successfully")
                break
            except SystemExit:
                raise
            except Exception as e:
                print(f"  -> Attempt {attempt} failed: {mask(str(e))}")
                if attempt < config.MAX_RETRIES:
                    print(f"  -> Waiting {config.RETRY_WAIT_SECONDS}s before retry...")
                    time.sleep(config.RETRY_WAIT_SECONDS)
                else:
                    fail_and_notify(
                        job,
                        f"[Step 16] HTML to PDF service request failed — {e}",
                        **kw,
                    )
        try:
            print(f"  -> Decoding PDF from base64...")
            pdf_bytes = base64.b64decode(pdf_base64)
            print(f"  -> Writing PDF to temp file...")
            tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp_pdf.write(pdf_bytes)
            tmp_pdf.close()
            pdf_path = tmp_pdf.name
            print(f"  -> PDF saved to: {mask(pdf_path)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 16] Writing PDF to temp file — {e}", **kw)
        print(f"  -> OK ({len(pdf_bytes)} bytes)")

        print("  ")
        print(f"[Step 17] Sending CV email to {mask(company.get('email', ''), 'email')}...")
        try:
            subject = (
                f"Candidature — {job.get('targetPosition', '')} | "
                f"{profile.get('firstName', '')} {profile.get('lastName', '')}"
            )
            print(f"  -> Subject: {mask(subject)}")
            print(f"  -> Sending via SMTP...")
            send_email(
                company["email"],
                subject,
                f"<pre>{_html_escape(message_text)}</pre>",
                smtp_email,
                smtp_password,
                attachment_path=pdf_path,
            )
            print("  -> Email sent successfully")
        except SystemExit:
            raise
        except Exception as e:
            try:
                emails.increment_email_stats(_claimed_email_id, "failed")
            except SystemExit:
                raise
            except Exception as inc_e:
                fail_and_notify(
                    job,
                    f"[Step 17] Email usage stats after failed send — {inc_e}",
                    **kw,
                )
            fail_and_notify(
                job,
                f"[Step 17] Failed to send CV email via SMTP — {e}",
                email_to_deactivate=email_config,
                **kw,
            )
        try:
            emails.increment_email_stats(_claimed_email_id, "success")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 17] Email usage stats after successful send — {e}", **kw)

        print("  ")
        print("[Step 18] Updating job as sent...")
        try:
            jobs.mark_sent(
                job_id,
                message_text,
                email_id=_claimed_email_id,
                cv_api_key_id=_claimed_cv_api_key_id,
                msg_api_key_id=_claimed_msg_api_key_id or _claimed_cv_api_key_id,
            )
            print(f"  -> Job marked as sent (email_id: {mask(_claimed_email_id)}, cv_key_id: {mask(_claimed_cv_api_key_id)}, msg_key_id: {mask(_claimed_msg_api_key_id or _claimed_cv_api_key_id)})")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 18] Updating job as sent — {e}", **kw)
        print("  -> OK (status: sent)")

        print("  ")
        print("[Step 19] Sending confirmation email...")
        try:
            confirm_subject = (
                f"✅ CV envoyé — {job.get('targetPosition', '')} @ {company.get('name', '')}"
            )
            print(f"  -> Confirmation subject: {mask(confirm_subject)}")
            ctx = build_context_html(
                job,
                company=company,
                cv_provider=cv_provider,
                msg_provider=msg_provider,
                cv_api_key=cv_api_key,
                msg_api_key=msg_api_key,
                email_config=email_config,
            )
            confirm_body = (
                f"<h2>✅ CV envoyé avec succès !</h2>"
                f"<p>Votre CV a été envoyé à l'entreprise <strong>{_html_escape(company.get('name', ''))}</strong>.</p>"
                f"{format_smtp_line(smtp_email)}"
                f"<p>📅 Date : {_html_escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>"
                f"<hr/>"
                f"{ctx}"
                f"<hr/><h3>Message envoyé</h3>"
                f"<pre style=\"background:#f5f5f5;padding:12px;border-radius:6px;font-size:13px;\">"
                f"{_html_escape(message_text)}</pre>"
            )
            print(f"  -> Sending confirmation to: {mask(config.NOTIFICATION_EMAIL, 'email')}...")
            send_email(
                config.NOTIFICATION_EMAIL,
                confirm_subject,
                confirm_body,
                smtp_email,
                smtp_password,
                attachment_path=pdf_path,
            )
            print(f"  -> Confirmation sent successfully (to: {mask(config.NOTIFICATION_EMAIL, 'email')})")
        except SystemExit:
            raise
        except Exception as e:
            print(f"  -> [WARN] [Step 19] Confirmation email failed (job already sent): {mask(str(e))}")
            try:
                ce, cp = _smtp_pair(smtp_email, smtp_password)
                if ce and cp and config.NOTIFICATION_EMAIL:
                    send_email(
                        config.NOTIFICATION_EMAIL,
                        "⚠️ Confirmation email failed (job was sent)",
                        f"<p>{_html_escape(e)}</p><p>Check logs; job status should already be <code>sent</code>.</p>",
                        ce,
                        cp,
                    )
            except Exception:
                pass

        print("---------------")
        print(f"✅ DONE — {mask(job_target_position)} @ {mask(company.get('name', ''))}")

    except SystemExit:
        raise
    except Exception as e:
        fail_and_notify(
            job,
            f"[Workflow] Unexpected error — {e}",
            **_notify_kw(
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                email_config=email_config,
                cv_api_key=cv_api_key,
                msg_api_key=msg_api_key,
                cv_provider=cv_provider,
                msg_provider=msg_provider,
                company=company,
            ),
        )
    finally:
        _release_claimed_resources()
        _current_job_id = None


if __name__ == "__main__":
    main()
