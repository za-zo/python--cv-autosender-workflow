import base64
import json
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
from helpers.scraper import scrape_website


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

def _handle_exit(signum, frame):
    """Release claimed job on interrupt/terminate, then exit."""
    if _current_job_id:
        print(f"\n  -> Releasing job {mask(_current_job_id)}...")
        try:
            jobs.release_job(_current_job_id)
        except Exception:
            pass
    print("  -> Exited.")
    sys.exit(1)


def fail_and_notify(job, reason, api_key_to_deactivate=None, smtp_email=None, smtp_password=None):
    """Mark job as failed, optionally deactivate an API key, send error email."""
    job_id = str(job["_id"])

    if api_key_to_deactivate:
        try:
            ai_api_keys.deactivate_api_key(str(api_key_to_deactivate["_id"]))
        except Exception:
            pass

    try:
        jobs.mark_failed(job_id, reason)
    except Exception:
        pass

    try:
        api_key_info = ""
        if api_key_to_deactivate:
            api_key_json = mask(json.dumps(api_key_to_deactivate, default=str, indent=2), "json")
            api_key_info = (
                f"<h3>API Key Info:</h3>"
                f"<pre>{api_key_json}</pre>"
            )

        job_json = mask(json.dumps(job, default=str, indent=2), "json")
        body = (
            f"<h2>❌ Job Failed</h2>"
            f"<p><strong>Reason:</strong> {_html_escape(reason)}</p>"
            f"<h3>Job Info:</h3>"
            f"<pre>{job_json}</pre>"
            f"{api_key_info}"
        )
        if smtp_email and smtp_password:
            send_email(
                config.NOTIFICATION_EMAIL,
                f"❌ Job Failed — {reason}",
                body,
                smtp_email,
                smtp_password,
            )
        else:
            print("  -> [WARN] No SMTP credentials available, skipping failure notification email.")
    except Exception:
        pass

    print(f"  -> [FAIL] {mask(reason)}")
    exit(1)


def call_ai_with_retries(provider_module, api_key, system_msg, user_msg):
    """Call AI provider with retry logic."""
    last_error = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return provider_module.call(api_key, system_msg, user_msg)
        except Exception as e:
            last_error = e
            if attempt < config.MAX_RETRIES:
                print(f"  -> Retry {attempt}/{config.MAX_RETRIES} failed, waiting {config.RETRY_WAIT_SECONDS}s...")
                time.sleep(config.RETRY_WAIT_SECONDS)
    raise last_error


def main():
    global _current_job_id
    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)

    # ── Step 01: Claim a Job ──────────────────────────────────────────────
    print("[Step 01] Claiming a job...")
    job = jobs.claim_job()
    if not job:
        print("  -> No active job found. Exiting.")
        print("---------------")
        return

    job_target_position = str(job.get("targetPosition", ""))
    job_id = str(job["_id"])
    _current_job_id = job_id
    print(f"  -> Claimed: {mask(job_target_position)} | {mask(job_id)}")

    try:
        # ── Step 02: Read Email Config ──────────────────────────────────────
        print("  ")
        print("[Step 02] Reading email config...")
        email_id = job.get("emailId")
        if not email_id:
            fail_and_notify(job, "Email ID is missing from job")
        email_config = emails.get_email(email_id)
        if not email_config:
            fail_and_notify(job, "Email config not found")
        if not email_config.get("active", False):
            fail_and_notify(job, "Email config is INACTIVE")
        smtp_email = email_config["smtp_email"]
        smtp_password = email_config["smtp_password"]
        print(f"  -> Email: {mask(smtp_email, 'email')} | {mask(smtp_password, 'secret')}")

        # ── Step 03: Read CV API Key ──────────────────────────────────────
        print("  ")
        print("[Step 03] Reading CV API key...")
        cv_api_key_id = job.get("ai_api_key_id_for_cv_gen")
        if not cv_api_key_id:
            fail_and_notify(job, "CV API Key ID is missing from job", smtp_email=smtp_email, smtp_password=smtp_password)
        cv_api_key = ai_api_keys.get_api_key(cv_api_key_id)
        if not cv_api_key:
            fail_and_notify(job, "CV API Key not found", smtp_email=smtp_email, smtp_password=smtp_password)
        print(f"  -> Key: {mask(cv_api_key.get('name', ''))} | {mask(cv_api_key.get('apiKey', ''), 'secret')} | usage: {cv_api_key.get('usageCount', 0)}")

        # ── Step 04: Read Message API Key ─────────────────────────────────
        print("  ")
        print("[Step 04] Reading Message API key...")
        msg_api_key_id = job.get("ai_api_key_id_for_message_gen")
        if not msg_api_key_id:
            fail_and_notify(job, "Message API Key ID is missing from job", smtp_email=smtp_email, smtp_password=smtp_password)
        msg_api_key = ai_api_keys.get_api_key(msg_api_key_id)
        if not msg_api_key:
            fail_and_notify(job, "Message API Key not found", smtp_email=smtp_email, smtp_password=smtp_password)
        print(f"  -> Key: {mask(msg_api_key.get('name', ''))} | {mask(msg_api_key.get('apiKey', ''), 'secret')} | usage: {msg_api_key.get('usageCount', 0)}")

        # ── Step 05: Check CV API Key is Active ───────────────────────────
        print("  ")
        print("[Step 05] Checking CV API key is active...")
        cv_active = cv_api_key.get("active", False)
        print(f"  -> active: {cv_active}")
        if not cv_active:
            fail_and_notify(job, "CV API Key is INACTIVE", smtp_email=smtp_email, smtp_password=smtp_password)

        # ── Step 06: Check Message API Key is Active ──────────────────────
        print("  ")
        print("[Step 06] Checking Message API key is active...")
        msg_active = msg_api_key.get("active", False)
        print(f"  -> active: {msg_active}")
        if not msg_active:
            fail_and_notify(job, "Message API Key is INACTIVE", smtp_email=smtp_email, smtp_password=smtp_password)

        # ── Step 07: Read CV API Key Provider ─────────────────────────────
        print("  ")
        print("[Step 07] Reading CV API key provider...")
        cv_provider = providers.get_provider(cv_api_key["provider"])
        if not cv_provider:
            fail_and_notify(job, "CV API Key Provider not found", smtp_email=smtp_email, smtp_password=smtp_password)
        print(f"  -> Provider: {mask(cv_provider.get('name', ''))}")

        # ── Step 08: Read Message API Key Provider ────────────────────────
        print("  ")
        print("[Step 08] Reading Message API key provider...")
        msg_provider = providers.get_provider(msg_api_key["provider"])
        if not msg_provider:
            fail_and_notify(job, "Message API Key Provider not found", smtp_email=smtp_email, smtp_password=smtp_password)
        print(f"  -> Provider: {mask(msg_provider.get('name', ''))}")

        # ── Step 09: Read Profile ─────────────────────────────────────────
        print("  ")
        print("[Step 09] Reading profile...")
        profile = profiles.get_profile()
        if not profile:
            fail_and_notify(job, "Profile not found", smtp_email=smtp_email, smtp_password=smtp_password)
        print(f"  -> {mask(profile.get('firstName', ''))} {mask(profile.get('lastName', ''))}")

        # ── Step 10: Read Company ─────────────────────────────────────────
        print("  ")
        print("[Step 10] Reading company...")
        company = companies.get_company(job["companyId"])
        if not company:
            fail_and_notify(job, "Company not found", smtp_email=smtp_email, smtp_password=smtp_password)
        print(f"  -> {mask(company.get('name', ''))} | {mask(company.get('email', ''), 'email')}")

        # ── Step 11: Scrape Company Website ───────────────────────────────
        print("  ")
        print("[Step 11] Scraping company website...")
        web_content = scrape_website(company.get("website"))
        if web_content:
            print(f"  -> OK ({len(web_content)} chars)")
        else:
            print(f"  -> Skipped (no content)")

        # ── Step 12: Build CV Prompt ──────────────────────────────────────
        print("  ")
        print("[Step 12] Building CV prompt...")
        cv_system_msg, cv_user_msg = build_cv_prompt(profile, company, job, web_content)
        print(f"  -> OK (prompt: {len(cv_user_msg)} chars)")

        # ── Step 13: Generate CV via AI API ───────────────────────────────
        print("  ")
        print(f"[Step 13] Generating CV via {mask(cv_provider['name'])}...")
        cv_provider_module = get_provider_module(cv_provider["name"])
        try:
            cv_raw_response = call_ai_with_retries(
                cv_provider_module, cv_api_key["apiKey"], cv_system_msg, cv_user_msg
            )
            print("  -> OK")
        except Exception as e:
            fail_and_notify(
                job,
                f"CV generation AI API error: {cv_provider['name']} returned error — {e}",
                api_key_to_deactivate=cv_api_key,
                smtp_email=smtp_email, smtp_password=smtp_password,
            )

        # ── Step 14: Parse CV Response ────────────────────────────────────
        print("  ")
        print("[Step 14] Parsing CV response...")
        try:
            cv_data = parse_cv_response(cv_provider["name"], cv_raw_response)
            skills = cv_data.get("skills", [])
            print(f"  -> OK (skills: {len(skills)}, projects: {len(cv_data.get('projects', []))})")
        except Exception as e:
            fail_and_notify(
                job,
                f"CV generation: AI response is not valid JSON — {e}",
                smtp_email=smtp_email, smtp_password=smtp_password,
            )

        # ── Step 15: Generate HTML CV ─────────────────────────────────────
        print("  ")
        print("[Step 15] Generating HTML CV...")
        html_content = generate_html_cv(cv_data, profile, job)
        print(f"  -> OK ({len(html_content)} chars)")

        # ── Step 16: Build Message Prompt ─────────────────────────────────
        print("  ")
        print("[Step 16] Building message prompt...")
        msg_system_msg, msg_user_msg, msg_lang = build_message_prompt(
            profile, company, job, web_content
        )
        print(f"  -> OK (lang: {mask(msg_lang)}, prompt: {len(msg_user_msg)} chars)")

        # ── Step 17: Generate Message via AI API ──────────────────────────
        print("  ")
        print(f"[Step 17] Generating message via {mask(msg_provider['name'])}...")
        msg_provider_module = get_provider_module(msg_provider["name"])
        try:
            msg_raw_response = call_ai_with_retries(
                msg_provider_module, msg_api_key["apiKey"], msg_system_msg, msg_user_msg
            )
            print("  -> OK")
        except Exception as e:
            fail_and_notify(
                job,
                f"Message generation AI API error: {msg_provider['name']} returned error — {e}",
                api_key_to_deactivate=msg_api_key,
                smtp_email=smtp_email, smtp_password=smtp_password,
            )

        # ── Step 18: Parse Message Response ───────────────────────────────
        print("  ")
        print("[Step 18] Parsing message response...")
        try:
            message_text = parse_message_response(msg_provider["name"], msg_raw_response)
            print(f"  -> OK ({len(message_text)} chars)")
        except Exception as e:
            fail_and_notify(
                job,
                f"Message generation: AI response parsing failed — {e}",
                smtp_email=smtp_email, smtp_password=smtp_password,
            )

        # ── Step 19: Convert HTML to PDF ──────────────────────────────────
        print("  ")
        print("[Step 19] Converting HTML to PDF...")
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
            except Exception as e:
                if attempt < config.MAX_RETRIES:
                    print(f"  -> Retry {attempt}/{config.MAX_RETRIES} failed, waiting {config.RETRY_WAIT_SECONDS}s...")
                    time.sleep(config.RETRY_WAIT_SECONDS)
                else:
                    fail_and_notify(job, f"HTML to PDF conversion failed — {e}", smtp_email=smtp_email, smtp_password=smtp_password)

        pdf_bytes = base64.b64decode(pdf_base64)
        tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp_pdf.write(pdf_bytes)
        tmp_pdf.close()
        pdf_path = tmp_pdf.name
        print(f"  -> OK ({len(pdf_bytes)} bytes)")

        # ── Step 20: Send CV Email via SMTP ───────────────────────────────
        print("  ")
        print(f"[Step 20] Sending CV email to {mask(company.get('email', ''), 'email')}...")
        subject = (
            f"Candidature — {job.get('targetPosition', '')} | "
            f"{profile.get('firstName', '')} {profile.get('lastName', '')}"
        )
        try:
            send_email(
                company["email"],
                subject,
                f"<pre>{_html_escape(message_text)}</pre>",
                smtp_email,
                smtp_password,
                attachment_path=pdf_path,
            )
            print("  -> OK")
        except Exception as e:
            fail_and_notify(job, f"Failed to send CV email via SMTP — {e}", smtp_email=smtp_email, smtp_password=smtp_password)

        # ── Step 21: Update Job as Sent ───────────────────────────────────
        print("  ")
        print("[Step 21] Updating job as sent...")
        jobs.mark_sent(job_id, message_text)
        print("  -> OK (status: sent)")

        # ── Step 22: Send Confirmation Email ──────────────────────────────
        print("  ")
        print("[Step 22] Sending confirmation email...")
        confirm_subject = (
            f"✅ CV envoyé — {job.get('targetPosition', '')} @ {company.get('name', '')}"
        )
        confirm_body = (
            f"<h2>✅ CV envoyé avec succès !</h2>"
            f"<p>Votre CV a été envoyé à l'entreprise <strong>{_html_escape(company.get('name', ''))}</strong>.</p>"
            f"<p>📧 Email : {_html_escape(company.get('email', ''))}</p>"
            f"<p>💼 Poste visé : {_html_escape(job.get('targetPosition', ''))}</p>"
            f"<p>📅 Date : {_html_escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>"
            f"<hr/><h3>Message envoyé :</h3>"
            f"<pre style=\"background:#f5f5f5;padding:12px;border-radius:6px;font-size:13px;\">"
            f"{_html_escape(message_text)}</pre>"
        )
        try:
            send_email(
                config.NOTIFICATION_EMAIL,
                confirm_subject,
                confirm_body,
                smtp_email,
                smtp_password,
                attachment_path=pdf_path,
            )
            print(f"  -> OK (to: {mask(config.NOTIFICATION_EMAIL, 'email')})")
        except Exception:
            print("  -> [WARN] Confirmation email failed, but job was already sent.")

        print("---------------")
        print(f"✅ DONE — {mask(job_target_position)} @ {mask(company.get('name', ''))}")

    except SystemExit:
        raise
    except Exception as e:
        reason = f"Unexpected error: {e}"
        fail_and_notify(job, reason)


if __name__ == "__main__":
    main()
