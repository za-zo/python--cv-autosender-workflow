import signal
import sys
import time

import config
from ai import get_provider_module
from ai.base import build_contact_message_prompt, parse_message_response
from db import ai_api_keys, contacts, contact_messages, emails, profiles, providers
from email_verifier import EmailVerifier
from helpers.email_sender import send_email
from helpers.notification_body import (
    build_contact_context_html,
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


def _cv_attachment_path(lang: str):
    raw = (lang or "").lower().strip()
    if raw in ("english", "anglais", "en"):
        return "statics/cv-en.pdf"
    return "statics/cv-fr.pdf"


def _html_escape(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


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
    msg_api_key=None,
    msg_provider=None,
    profile=None,
    contact=None,
):
    """Keyword args for fail_and_notify from current workflow state."""
    return {
        "smtp_email": smtp_email,
        "smtp_password": smtp_password,
        "email_config": email_config,
        "msg_api_key": msg_api_key,
        "msg_provider": msg_provider,
        "profile": profile,
        "contact": contact,
    }


def fail_and_notify(
    msg,
    reason,
    *,
    api_key_to_deactivate=None,
    api_key_deactivate_desc="API key",
    email_to_deactivate=None,
    smtp_email=None,
    smtp_password=None,
    profile=None,
    contact=None,
    email_config=None,
    msg_provider=None,
    msg_api_key=None,
    updates_made=None,
):
    """Mark contact message as failed, optionally deactivate resources, send notification."""
    msg_id = str(msg.get("_id")) if msg else None
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

    if msg_id:
        print("  -> Marking contact message as failed...")
        try:
            contact_messages.mark_failed(msg_id, reason)
            updates.append("Contact message was updated: status=failed, active=false, in_use=false.")
            print("  -> Contact message marked as failed.")
        except Exception as e:
            print(f"  -> [WARN] Failed to mark contact message as failed: {mask(str(e))}")

    pair_e, pair_p = _smtp_pair(smtp_email, smtp_password)
    if pair_e and pair_p and config.ENABLE_NOTIFICATIONS and config.NOTIFICATION_EMAIL:
        try:
            ctx = build_contact_context_html(
                msg,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )
            body = (
                f"<h2>❌ Contact message failed</h2>"
                f"<p><strong>Reason:</strong> {_html_escape(reason)}</p>"
                f"<p>📅 Date : {_html_escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>"
                f"<hr/>"
                f"{ctx}"
                f"{format_updates_html(updates)}"
            )
            subj = "❌ Contact message failed — " + reason.replace("\n", " ").strip()[:200]
            send_email(
                config.NOTIFICATION_EMAIL,
                subj,
                body,
                pair_e,
                pair_p,
            )
        except Exception as e:
            print(f"  -> [WARN] Failed to send failure notification via primary SMTP: {mask(str(e))}")
            # Fallback to global notification SMTP if different
            ne, np = config.NOTIFICATION_SMTP_EMAIL, config.NOTIFICATION_SMTP_PASSWORD
            if ne and np and (ne != pair_e or np != pair_p):
                print(f"  -> Attempting fallback notification via global SMTP {mask(ne, 'email')}...")
                try:
                    send_email(
                        config.NOTIFICATION_EMAIL,
                        subj,
                        body,
                        ne,
                        np,
                    )
                    print("  -> Fallback notification sent.")
                except Exception as fe:
                    print(f"  -> [WARN] Fallback notification also failed: {mask(str(fe))}")
    else:
        if not config.ENABLE_NOTIFICATIONS:
            print("  -> Notifications disabled, skipping failure notification email.")
        else:
            print("  -> [WARN] No SMTP credentials or NOTIFICATION_EMAIL, skipping failure notification email.")

    print(f"  -> [FAIL] {mask(reason)}")
    sys.exit(1)


_current_msg_id = None
_claimed_email_id = None
_claimed_msg_api_key_id = None


def _reset_claimed_ids():
    global _claimed_email_id, _claimed_msg_api_key_id
    _claimed_email_id = None
    _claimed_msg_api_key_id = None


def _release_claimed_resources():
    global _claimed_email_id, _claimed_msg_api_key_id
    if _claimed_msg_api_key_id:
        print(f"  -> Releasing message API key {mask(_claimed_msg_api_key_id)}...")
        try:
            ai_api_keys.release_api_key_in_use(_claimed_msg_api_key_id)
            print(f"  -> Message API key released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release message API key: {mask(str(e))}")
        _claimed_msg_api_key_id = None
    if _claimed_email_id:
        print(f"  -> Releasing email {mask(_claimed_email_id)}...")
        try:
            emails.release_email_in_use(_claimed_email_id)
            print(f"  -> Email released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release email: {mask(str(e))}")
        _claimed_email_id = None


def _handle_exit(signum, frame):
    """Release claimed message and pool resources on interrupt/terminate, then exit."""
    sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM" if signum == signal.SIGTERM else f"signal {signum}"
    print(f"\n  -> Received {sig_name}, initiating cleanup...")
    if _current_msg_id:
        print(f"  -> Releasing contact message {mask(_current_msg_id)}...")
        try:
            contact_messages.release_contact_message(_current_msg_id)
            print(f"  -> Contact message released.")
        except Exception as e:
            print(f"  -> [WARN] Failed to release contact message: {mask(str(e))}")
    _release_claimed_resources()
    print("  -> Exited.")
    sys.exit(1)


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
    global _current_msg_id, _claimed_email_id, _claimed_msg_api_key_id
    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)

    print("[Step 01] Claiming a contact message...")
    try:
        msg = contact_messages.claim_available_contact_message()
    except Exception as e:
        print(f"  -> [Step 01] Claim contact message failed: {mask(str(e))}")
        print("---------------")
        return
    if not msg:
        print("  -> No pending contact message. Exiting.")
        print("---------------")
        return

    msg_id = str(msg["_id"])
    _current_msg_id = msg_id
    _reset_claimed_ids()
    print(f"  -> ContactMessage claimed: {mask(msg_id)} | contactId: {mask(msg.get('contactId', ''))}")

    smtp_email = smtp_password = None
    email_config = None
    msg_api_key = None
    msg_provider = None
    profile = None
    contact = None
    updates_made = []

    try:
        print("  ")
        print("[Step 02] Reading profile...")
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
                msg,
                f"[Step 02] Reading profile — {e}",
                **_notify_kw(profile=profile),
            )
        if not profile:
            fail_and_notify(
                msg,
                "[Step 02] Profile not found (empty result)",
                **_notify_kw(profile=None),
            )

        print("  ")
        print("[Step 03] Reading contact...")
        try:
            contact = contacts.get_contact(msg["contactId"])
            if contact:
                print(f"  -> Contact loaded: {mask(contact.get('complete_name', ''))} | {mask(contact.get('email', ''), 'email')}")
            else:
                print(f"  -> [WARN] Contact not found for ID: {mask(msg.get('contactId', ''))}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 03] Reading contact — {e}",
                **_notify_kw(profile=profile, contact=contact),
            )
        if not contact:
            fail_and_notify(
                msg,
                f"Contact not found for contactId={msg.get('contactId')}",
                **_notify_kw(profile=profile, contact=None),
            )

        contact_email = contact.get("email", "")
        print("  ")
        print("[Step 03b] Verifying contact email...")
        try:
            verifier = EmailVerifier()
            result = verifier.verify(contact_email)
            if not result["valid"]:
                reason = f"Contact email verification failed: {result['reason']}"
                fail_and_notify(
                    msg,
                    reason,
                    **_notify_kw(
                        smtp_email=smtp_email,
                        smtp_password=smtp_password,
                        profile=profile,
                        contact=contact,
                        email_config=email_config,
                        msg_api_key=msg_api_key,
                    ),
                )
            print(f"  -> Contact email verified: {mask(contact_email, 'email')}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 03b] Contact email verification — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    profile=profile,
                    contact=contact,
                    email_config=email_config,
                    msg_api_key=msg_api_key,
                ),
            )

        print("  ")
        print("[Step 04] Claiming email config...")
        try:
            raw_email_id = msg.get("emailId")
            print(f"  -> Looking for email (requested ID: {mask(raw_email_id) if raw_email_id else 'any available'})...")
            if raw_email_id:
                email_config = emails.claim_email_by_id(raw_email_id)
            else:
                email_config = emails.claim_available_email()
            if not email_config:
                print(f"  -> [WARN] Failed to claim email config")
                fail_and_notify(
                    msg,
                    "No available email config (active=true and not in_use)",
                    **_notify_kw(profile=profile, contact=contact),
                )
            _claimed_email_id = str(email_config["_id"])
            smtp_email = email_config["smtp_email"]
            smtp_password = email_config["smtp_password"]
            print(f"  -> Email claimed: {mask(smtp_email, 'email')} | ID: {mask(_claimed_email_id)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 04] Claiming email config — {e}",
                **_notify_kw(profile=profile, contact=contact, email_config=email_config),
            )

        print("  ")
        print("[Step 05] Claiming message API key...")
        try:
            raw_msg_id = msg.get("ai_api_key_id_for_message_gen")
            print(f"  -> Looking for message API key (requested ID: {mask(raw_msg_id) if raw_msg_id else 'any available'})...")
            if raw_msg_id:
                msg_api_key = ai_api_keys.claim_api_key_by_id(raw_msg_id)
            else:
                msg_api_key = ai_api_keys.claim_available_api_key()
            if not msg_api_key:
                print(f"  -> [WARN] Failed to claim message API key")
                fail_and_notify(
                    msg,
                    "No available message API key (active=true and not in_use)",
                    **_notify_kw(
                        smtp_email=smtp_email,
                        smtp_password=smtp_password,
                        profile=profile,
                        contact=contact,
                        email_config=email_config,
                    ),
                )
            _claimed_msg_api_key_id = str(msg_api_key["_id"])
            print(f"  -> Message API key claimed: {mask(msg_api_key.get('name', ''))} | ID: {mask(_claimed_msg_api_key_id)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 05] Claiming message API key — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    profile=profile,
                    contact=contact,
                    email_config=email_config,
                    msg_api_key=msg_api_key,
                ),
            )

        print("  ")
        print("[Step 06] Reading message API key provider...")
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
                msg,
                f"[Step 06] Reading message API key provider — {e}",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    profile=profile,
                    contact=contact,
                    email_config=email_config,
                    msg_api_key=msg_api_key,
                ),
            )
        if not msg_provider:
            fail_and_notify(
                msg,
                "Message provider not found for message API key",
                **_notify_kw(
                    smtp_email=smtp_email,
                    smtp_password=smtp_password,
                    profile=profile,
                    contact=contact,
                    email_config=email_config,
                    msg_api_key=msg_api_key,
                ),
            )

        kw = _notify_kw(
            smtp_email=smtp_email,
            smtp_password=smtp_password,
            email_config=email_config,
            msg_api_key=msg_api_key,
            msg_provider=msg_provider,
            profile=profile,
            contact=contact,
        )

        print("  ")
        print("[Step 07] Building outreach prompt...")
        try:
            msg_system, msg_user, lang = build_contact_message_prompt(profile, contact, msg)
            print(f"  -> System prompt: {len(msg_system)} chars, User prompt: {len(msg_user)} chars, Language: {mask(lang)}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(msg, f"[Step 07] Building outreach prompt — {e}", **kw)
        print(f"  -> OK (lang: {mask(lang)}, prompt: {len(msg_user)} chars)")

        print("  ")
        print(f"[Step 08] Generating message via {mask(msg_provider['name'])}...")
        try:
            msg_provider_module = get_provider_module(msg_provider["name"])
            print(f"  -> Provider module loaded: {mask(msg_provider['name'])}")
        except SystemExit:
            raise
        except Exception as e:
            fail_and_notify(msg, f"[Step 08] Loading message provider module — {e}", **kw)
        
        try:
            print(f"  -> Calling AI with model: {mask(msg_provider.get('model_name', 'default'))}...")
            msg_raw_response = call_ai_with_retries(
                msg_provider_module,
                msg_api_key["apiKey"],
                msg_system,
                msg_user,
                model_name=msg_provider.get("model_name"),
            )
            message_text = parse_message_response(msg_provider["name"], msg_raw_response)
            print(f"  -> AI response received and parsed: {len(message_text)} chars")
        except SystemExit:
            raise
        except Exception as e:
            try:
                ai_api_keys.increment_api_key_stats(_claimed_msg_api_key_id, "failed")
            except Exception:
                pass
            fail_and_notify(
                msg,
                f"[Step 08] Generating message via provider — {e}",
                api_key_to_deactivate=msg_api_key,
                api_key_deactivate_desc="Message generation API key",
                **kw,
            )
        try:
            ai_api_keys.increment_api_key_stats(_claimed_msg_api_key_id, "success")
        except Exception as e:
            fail_and_notify(msg, f"[Step 08] Message API key usage stats after success — {e}", **kw)

        print("  ")
        print(f"[Step 09] Sending outreach email to {mask(contact.get('email', ''), 'email')}...")
        subject = f"{profile.get('firstName', '')} {profile.get('lastName', '')} — Introduction"
        attachment = _cv_attachment_path(lang)
        try:
            send_email(
                contact["email"],
                subject,
                f"<pre>{_html_escape(message_text)}</pre>",
                smtp_email,
                smtp_password,
                attachment_path=attachment,
            )
            print(f"  -> Email sent successfully to {mask(contact['email'], 'email')}")
        except Exception as e:
            try:
                emails.increment_email_stats(_claimed_email_id, "failed")
            except Exception:
                pass
            fail_and_notify(
                msg,
                f"[Step 09] Failed to send outreach email via SMTP — {e}",
                email_to_deactivate=email_config,
                **kw,
            )
        try:
            emails.increment_email_stats(_claimed_email_id, "success")
        except Exception as e:
            fail_and_notify(msg, f"[Step 09] Email usage stats after successful send — {e}", **kw)

        print("  ")
        print("[Step 10] Marking contact message as sent...")
        try:
            contact_messages.mark_sent(
                msg_id,
                message_text,
                email_id=_claimed_email_id,
                ai_api_key_id_for_message_gen=_claimed_msg_api_key_id,
            )
            updates_made.append("Contact message was updated: status=sent, active=false, in_use=false.")
            print("  -> Contact message marked as sent.")
        except Exception as e:
            fail_and_notify(msg, f"[Step 10] Marking contact message as sent — {e}", **kw)

        print("  ")
        print("[Step 11] Sending confirmation email...")
        try:
            contact_email = contact.get("email", "")
            contact_name = (contact.get("complete_name") or "").strip()
            if contact_name:
                confirm_subject = f"✅ Contact message sent — {contact_name} <{contact_email}>".strip()
            else:
                confirm_subject = f"✅ Contact message sent — <{contact_email}>".strip()
            
            ctx = build_contact_context_html(
                msg,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )
            confirm_body = (
                f"<h2>✅ Contact message sent successfully!</h2>"
                f"<p>Recipient: <strong>{_html_escape(contact_name) if contact_name else '—'}</strong> "
                f"&lt;{_html_escape(contact_email)}&gt;</p>"
                f"{format_smtp_line(smtp_email)}"
                f"<p>📅 Date : {_html_escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>"
                f"<hr/>"
                f"{ctx}"
                f"{format_updates_html(updates_made)}"
                f"<hr/><h3>Message sent</h3>"
                f"<pre style=\"background:#f5f5f5;padding:12px;border-radius:6px;font-size:13px;\">"
                f"{_html_escape(message_text)}</pre>"
            )
            if not config.ENABLE_NOTIFICATIONS:
                print("  -> Notifications disabled, skipping confirmation email.")
            elif not config.NOTIFICATION_EMAIL:
                print("  -> [WARN] NOTIFICATION_EMAIL is not set, skipping confirmation email.")
            else:
                pair_e, pair_p = _smtp_pair(smtp_email, smtp_password)
                if pair_e and pair_p:
                    send_email(
                        config.NOTIFICATION_EMAIL,
                        confirm_subject,
                        confirm_body,
                        pair_e,
                        pair_p,
                        attachment_path=attachment,
                    )
                    print(f"  -> Confirmation sent successfully (to: {mask(config.NOTIFICATION_EMAIL, 'email')})")
                else:
                    print("  -> [WARN] No SMTP credentials for confirmation email.")
        except Exception as e:
            print(f"  -> [WARN] [Step 11] Confirmation email failed (message already sent): {mask(str(e))}")

        print("---------------")
        print(f"✅ DONE — sent to {mask(contact.get('email', ''), 'email')}")

    except SystemExit:
        raise
    except Exception as e:
        fail_and_notify(msg, f"[Workflow] Unexpected error — {e}", updates_made=updates_made, **kw)
    finally:
        _release_claimed_resources()
        _current_msg_id = None


if __name__ == "__main__":
    main()
