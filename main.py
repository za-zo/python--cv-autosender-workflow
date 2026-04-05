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
        try:
            ai_api_keys.release_api_key_in_use(_claimed_msg_api_key_id)
        except Exception:
            pass
        _claimed_msg_api_key_id = None
    if _claimed_cv_api_key_id:
        try:
            ai_api_keys.release_api_key_in_use(_claimed_cv_api_key_id)
        except Exception:
            pass
        _claimed_cv_api_key_id = None
    if _claimed_email_id:
        try:
            emails.release_email_in_use(_claimed_email_id)
        except Exception:
            pass
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
    if _current_job_id:
        print(f"\n  -> Releasing job {mask(_current_job_id)}...")
        try:
            jobs.release_job(_current_job_id)
        except Exception:
            pass
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
        try:
            ai_api_keys.deactivate_api_key(str(api_key_to_deactivate["_id"]))
            updates.append(
                f"{api_key_deactivate_desc} was deactivated (active=false, in_use=false)."
            )
        except Exception:
            pass

    if email_to_deactivate:
        try:
            emails.deactivate_email(str(email_to_deactivate["_id"]))
            updates.append("Email account was deactivated (active=false, in_use=false).")
        except Exception:
            pass

    try:
        jobs.mark_failed(job_id, reason)
        updates.append("Job was updated: status=failed, active=false, in_use=false.")
    except Exception:
        pass

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
    print(f"  -> Claimed: {mask(job_target_position)} | {mask(job_id)}")

    smtp_email = smtp_password = None
    email_config = None
    cv_api_key = msg_api_key = None
    cv_provider = msg_provider = None
    company = profile = None

    try:
        print("  ")
        print("[Step 02] Claiming email config...")
        try:
            raw_email_id = job.get("emailId")
            if raw_email_id:
                email_config = emails.claim_email_by_id(raw_email_id)
            else:
                email_config = emails.claim_available_email()
            if not email_config:
                _fail_email_claim(job, raw_email_id)
            _claimed_email_id = str(email_config["_id"])
            smtp_email = email_config["smtp_email"]
            smtp_password = email_config["smtp_password"]
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 02] Claiming email config — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                ),
            )
        print(f"  -> Email: {mask(smtp_email, 'email')} | {mask(smtp_password, 'secret')}")

        print("  ")
        print("[Step 03] Claiming CV API key...")
        try:
            raw_cv_id = job.get("ai_api_key_id_for_cv_gen")
            if raw_cv_id:
                cv_api_key = ai_api_keys.claim_api_key_by_id(raw_cv_id)
            else:
                cv_api_key = ai_api_keys.claim_available_api_key()
            if not cv_api_key:
                _fail_cv_key_claim(job, raw_cv_id, email_config, smtp_email, smtp_password)
            _claimed_cv_api_key_id = str(cv_api_key["_id"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 03] Claiming CV API key — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                ),
            )
        print(
            f"  -> Key: {mask(cv_api_key.get('name', ''))} | "
            f"{mask(cv_api_key.get('apiKey', ''), 'secret')} | usage: {cv_api_key.get('usageCount', 0)}"
        )

        print("  ")
        print("[Step 04] Claiming message API key...")
        try:
            raw_msg_id = job.get("ai_api_key_id_for_message_gen")
            same_key_as_cv = raw_msg_id and raw_cv_id and str(raw_msg_id) == str(raw_cv_id)
            if same_key_as_cv:
                msg_api_key = cv_api_key
            elif raw_msg_id:
                msg_api_key = ai_api_keys.claim_api_key_by_id(raw_msg_id)
            else:
                msg_api_key = ai_api_keys.claim_available_api_key()
            if not msg_api_key:
                _fail_msg_key_claim(
                    job, raw_msg_id, email_config, smtp_email, smtp_password, cv_api_key
                )
            if not same_key_as_cv:
                _claimed_msg_api_key_id = str(msg_api_key["_id"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 04] Claiming message API key — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                ),
            )
        msg_key_stats_id = _claimed_msg_api_key_id or _claimed_cv_api_key_id
        print(
            f"  -> Key: {mask(msg_api_key.get('name', ''))} | "
            f"{mask(msg_api_key.get('apiKey', ''), 'secret')} | usage: {msg_api_key.get('usageCount', 0)}"
        )

        print("  ")
        print("[Step 05] Reading CV API key provider...")
        try:
            cv_provider = providers.get_provider(cv_api_key["provider"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 05] Reading CV API key provider — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                ),
            )
        if not cv_provider:
            fail_and_notify(
                job,
                "[Step 05] CV API key provider not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                ),
            )

        print("  ")
        print("[Step 06] Reading message API key provider...")
        try:
            msg_provider = providers.get_provider(msg_api_key["provider"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 06] Reading message API key provider — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                ),
            )
        if not msg_provider:
            fail_and_notify(
                job,
                "[Step 06] Message API key provider not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                ),
            )

        print("  ")
        print("[Step 07] Reading profile...")
        try:
            profile = profiles.get_profile()
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 07] Reading profile — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    msg_provider=msg_provider,
                ),
            )
        if not profile:
            fail_and_notify(
                job,
                "[Step 07] Profile not found (empty result)",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    email_config=email_config,
                    cv_api_key=cv_api_key,
                    msg_api_key=msg_api_key,
                    cv_provider=cv_provider,
                    msg_provider=msg_provider,
                ),
            )
        print(f"  -> {mask(profile.get('firstName', ''))} {mask(profile.get('lastName', ''))}")

        print("  ")
        print("[Step 08] Reading company...")
        try:
            company = companies.get_company(job["companyId"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                job,
                f"[Step 08] Reading company — {e}",
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
                "[Step 08] Company not found (empty result)",
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
        print(f"  -> {mask(company.get('name', ''))} | {mask(company.get('email', ''), 'email')}")

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
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 09] Building CV prompt — {e}", **kw)
        print(f"  -> OK (prompt: {len(cv_user_msg)} chars)")

        print("  ")
        print(f"[Step 10] Generating CV via {mask(cv_provider['name'])}...")
        try:
            cv_provider_module = get_provider_module(cv_provider["name"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 10] Loading CV provider module — {e}", **kw)
        try:
            cv_raw_response = call_ai_with_retries(
                cv_provider_module,
                cv_api_key["apiKey"],
                cv_system_msg,
                cv_user_msg,
                model_name=cv_provider.get("model_name"),
            )
            print("  -> OK")
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
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 13] Building message prompt — {e}", **kw)
        print(f"  -> OK (lang: {mask(msg_lang)}, prompt: {len(msg_user_msg)} chars)")

        print("  ")
        print(f"[Step 14] Generating message via {mask(msg_provider['name'])}...")
        try:
            msg_provider_module = get_provider_module(msg_provider["name"])
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(job, f"[Step 14] Loading message provider module — {e}", **kw)
        try:
            msg_raw_response = call_ai_with_retries(
                msg_provider_module,
                msg_api_key["apiKey"],
                msg_system_msg,
                msg_user_msg,
                model_name=msg_provider.get("model_name"),
            )
            print("  -> OK")
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
        pdf_base64 = None
        for attempt in range(1, config.MAX_RETRIES + 1):
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
                break
            except SystemExit:
                raise
            except Exception as e:
                if attempt < config.MAX_RETRIES:
                    print(f"  -> Retry {attempt}/{config.MAX_RETRIES} failed, waiting {config.RETRY_WAIT_SECONDS}s...")
                    time.sleep(config.RETRY_WAIT_SECONDS)
                else:
                    fail_and_notify(
                        job,
                        f"[Step 16] HTML to PDF service request failed — {e}",
                        **kw,
                    )
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp_pdf.write(pdf_bytes)
            tmp_pdf.close()
            pdf_path = tmp_pdf.name
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
            send_email(
                company["email"],
                subject,
                f"<pre>{_html_escape(message_text)}</pre>",
                smtp_email,
                smtp_password,
                attachment_path=pdf_path,
            )
            print("  -> OK")
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
            send_email(
                config.NOTIFICATION_EMAIL,
                confirm_subject,
                confirm_body,
                smtp_email,
                smtp_password,
                attachment_path=pdf_path,
            )
            print(f"  -> OK (to: {mask(config.NOTIFICATION_EMAIL, 'email')})")
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
