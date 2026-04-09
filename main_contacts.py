import signal
import sys
import time

import config
from ai import get_provider_module
from ai.base import build_contact_message_prompt, parse_message_response
from db import ai_api_keys, contacts, contact_messages, emails, profiles, providers
from helpers.email_sender import send_email


def mask(val, kind="str"):
    if not config.MASK_LOGS:
        return val
    s = str(val) if val else ""
    if not s:
        return ""
    if kind == "email":
        return "***@***.***"
    if kind == "secret":
        return "********"
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


def _dl_row(label, value):
    v = "—" if value is None else _html_escape(value)
    return f"<tr><td style=\"padding:4px 12px 4px 0;vertical-align:top;color:#555;\"><strong>{_html_escape(label)}</strong></td><td style=\"padding:4px 0;\">{v}</td></tr>"


def _section(title, rows_html):
    return (
        f"<h3 style=\"margin:16px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px;\">{_html_escape(title)}</h3>"
        f"<table style=\"border-collapse:collapse;font-size:13px;\">{rows_html}</table>"
    )


def build_contact_context_html(
    msg,
    *,
    profile=None,
    contact=None,
    email_config=None,
    msg_provider=None,
    msg_api_key=None,
):
    parts = []
    if msg is not None:
        rows = "".join(
            [
                _dl_row("_id", msg.get("_id")),
                _dl_row("contactId", msg.get("contactId")),
                _dl_row("type", msg.get("type")),
                _dl_row("notes", msg.get("notes")),
                _dl_row("language", msg.get("language")),
                _dl_row("status", msg.get("status")),
                _dl_row("sentAt", msg.get("sentAt")),
                _dl_row("gmailMessageId", msg.get("gmailMessageId")),
                _dl_row("failed_reason", msg.get("failed_reason")),
                _dl_row("emailId", msg.get("emailId")),
                _dl_row("ai_api_key_id_for_message_gen", msg.get("ai_api_key_id_for_message_gen")),
                _dl_row("createdAt", msg.get("createdAt")),
                _dl_row("updatedAt", msg.get("updatedAt")),
            ]
        )
        parts.append(_section("Contact message", rows))
    if contact is not None:
        rows = "".join(
            [
                _dl_row("_id", contact.get("_id")),
                _dl_row("email", contact.get("email")),
                _dl_row("complete_name", contact.get("complete_name")),
                _dl_row("description", contact.get("description")),
                _dl_row("companyId", contact.get("companyId")),
                _dl_row("createdAt", contact.get("createdAt")),
                _dl_row("updatedAt", contact.get("updatedAt")),
            ]
        )
        parts.append(_section("Contact", rows))
    if profile is not None:
        rows = "".join(
            [
                _dl_row("_id", profile.get("_id")),
                _dl_row("firstName", profile.get("firstName")),
                _dl_row("lastName", profile.get("lastName")),
                _dl_row("email", profile.get("email")),
                _dl_row("phone", profile.get("phone")),
                _dl_row("website", profile.get("website")),
                _dl_row("linkedin", profile.get("linkedin")),
            ]
        )
        parts.append(_section("Profile", rows))
    if email_config is not None:
        rows = "".join(
            [
                _dl_row("_id", email_config.get("_id")),
                _dl_row("smtp_email", email_config.get("smtp_email")),
                _dl_row("usage_count", email_config.get("usage_count")),
                _dl_row("successUsageCount", email_config.get("successUsageCount")),
                _dl_row("failedUsageCount", email_config.get("failedUsageCount")),
                _dl_row("createdAt", email_config.get("createdAt")),
            ]
        )
        parts.append(_section("Email (SMTP account)", rows))
    if msg_provider is not None:
        rows = "".join(
            [
                _dl_row("_id", msg_provider.get("_id")),
                _dl_row("name", msg_provider.get("name")),
                _dl_row("model_name", msg_provider.get("model_name")),
                _dl_row("createdAt", msg_provider.get("createdAt")),
            ]
        )
        parts.append(_section("Message provider", rows))
    if msg_api_key is not None:
        api_key_value = str(msg_api_key.get("apiKey") or "")
        masked_key = "****" if len(api_key_value) <= 4 else f"…{api_key_value[-4:]}"
        rows = "".join(
            [
                _dl_row("_id", msg_api_key.get("_id")),
                _dl_row("name", msg_api_key.get("name")),
                _dl_row("apiKey", masked_key),
                _dl_row("usageCount", msg_api_key.get("usageCount")),
                _dl_row("successUsageCount", msg_api_key.get("successUsageCount")),
                _dl_row("failedUsageCount", msg_api_key.get("failedUsageCount")),
                _dl_row("createdAt", msg_api_key.get("createdAt")),
            ]
        )
        parts.append(_section("AI API key (message generation)", rows))
    return "\n".join(parts)


def format_smtp_line(smtp_email):
    if not smtp_email:
        return ""
    return f"<p><strong>SMTP sender used:</strong> {_html_escape(smtp_email)}</p>"


def fail_and_notify(
    msg,
    reason,
    *,
    smtp_email=None,
    smtp_password=None,
    profile=None,
    contact=None,
    email_config=None,
    msg_provider=None,
    msg_api_key=None,
    updates_made=None,
):
    """Mark contact message as failed and send a structured notification email."""
    msg_id = str(msg.get("_id")) if msg else None
    updates = list(updates_made) if updates_made else []

    if msg_id:
        print("  -> Marking contact message as failed...")
        try:
            contact_messages.mark_failed(msg_id, reason)
            updates.append("Contact message was updated: status=failed, active=false, in_use=false.")
            print("  -> Contact message marked as failed.")
        except Exception as e:
            print(f"  -> [WARN] Failed to mark contact message as failed: {mask(str(e))}")

    pair_e, pair_p = _smtp_pair(smtp_email, smtp_password)
    try:
        ctx = build_contact_context_html(
            msg,
            profile=profile,
            contact=contact,
            email_config=email_config,
            msg_provider=msg_provider,
            msg_api_key=msg_api_key,
        )
        updates_html = ""
        if updates:
            items = "".join(f"<li>{_html_escape(u)}</li>" for u in updates)
            updates_html = (
                "<h3 style=\"margin:16px 0 8px;\">Updates applied</h3>"
                f"<ul style=\"margin:0;padding-left:20px;\">{items}</ul>"
            )
        body = (
            f"<h2>❌ Contact message failed</h2>"
            f"<p><strong>Reason:</strong> {_html_escape(reason)}</p>"
            f"<p>📅 Date : {_html_escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>"
            f"<hr/>"
            f"{ctx}"
            f"{updates_html}"
        )
        subj = "❌ Contact message failed — " + reason.replace("\n", " ").strip()[:200]
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
    sys.exit(1)


_current_msg_id = None
_claimed_email_id = None
_claimed_msg_api_key_id = None


def _release_claimed_resources():
    global _claimed_email_id, _claimed_msg_api_key_id
    if _claimed_msg_api_key_id:
        try:
            ai_api_keys.release_api_key_in_use(_claimed_msg_api_key_id)
        except Exception:
            pass
        _claimed_msg_api_key_id = None
    if _claimed_email_id:
        try:
            emails.release_email_in_use(_claimed_email_id)
        except Exception:
            pass
        _claimed_email_id = None


def _handle_exit(signum, frame):
    if _current_msg_id:
        try:
            contact_messages.release_contact_message(_current_msg_id)
        except Exception:
            pass
    _release_claimed_resources()
    sys.exit(1)


def main():
    global _current_msg_id, _claimed_email_id, _claimed_msg_api_key_id
    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)

    print("[Step 01] Claiming a contact message...")
    msg = contact_messages.claim_available_contact_message()
    if not msg:
        print("  -> No pending contact message. Exiting.")
        return

    msg_id = str(msg["_id"])
    _current_msg_id = msg_id
    print(f"  -> ContactMessage claimed: {mask(msg_id)} | contactId: {mask(msg.get('contactId', ''))}")

    smtp_email = smtp_password = None
    email_config = None
    msg_api_key = None
    msg_provider = None
    profile = None
    contact = None

    try:
        print("  ")
        print("[Step 02] Reading profile...")
        profile = profiles.get_profile()
        if not profile:
            fail_and_notify(msg, "Profile not found (db.profiles.find_one returned None)")

        print("  ")
        print("[Step 03] Reading contact...")
        contact = contacts.get_contact(msg["contactId"])
        if not contact:
            fail_and_notify(
                msg,
                f"Contact not found for contactId={msg.get('contactId')}",
                profile=profile,
            )

        print("  ")
        print("[Step 04] Claiming email config...")
        raw_email_id = msg.get("emailId")
        if raw_email_id:
            email_config = emails.claim_email_by_id(raw_email_id)
        else:
            email_config = emails.claim_available_email()
        if not email_config:
            fail_and_notify(
                msg,
                "No available email config (active=true and not in_use)",
                profile=profile,
                contact=contact,
            )
        _claimed_email_id = str(email_config["_id"])
        smtp_email = email_config["smtp_email"]
        smtp_password = email_config["smtp_password"]
        print(f"  -> Email claimed: {mask(smtp_email, 'email')} | ID: {mask(_claimed_email_id)}")

        print("  ")
        print("[Step 05] Claiming message API key...")
        raw_msg_id = msg.get("ai_api_key_id_for_message_gen")
        if raw_msg_id:
            msg_api_key = ai_api_keys.claim_api_key_by_id(raw_msg_id)
        else:
            msg_api_key = ai_api_keys.claim_available_api_key()
        if not msg_api_key:
            fail_and_notify(
                msg,
                "No available message API key (active=true and not in_use)",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
            )
        _claimed_msg_api_key_id = str(msg_api_key["_id"])
        print(f"  -> Message API key claimed: {mask(msg_api_key.get('name', ''))} | ID: {mask(_claimed_msg_api_key_id)}")

        print("  ")
        print("[Step 06] Reading message API key provider...")
        msg_provider = providers.get_provider(msg_api_key["provider"])
        if not msg_provider:
            fail_and_notify(
                msg,
                "Message provider not found for message API key",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_api_key=msg_api_key,
            )

        print("  ")
        print("[Step 07] Building outreach prompt...")
        try:
            msg_system, msg_user, lang = build_contact_message_prompt(profile, contact, msg)
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 07] Building outreach prompt — {e}",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )
        print(f"  -> Language: {mask(lang)} | Prompt: {len(msg_user)} chars")

        print("  ")
        print(f"[Step 08] Generating message via {mask(msg_provider['name'])}...")
        try:
            msg_provider_module = get_provider_module(msg_provider["name"])
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 08] Loading message provider module — {e}",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )
        try:
            msg_raw_response = msg_provider_module.call(
                msg_api_key["apiKey"],
                msg_system,
                msg_user,
                model_name=msg_provider.get("model_name"),
            )
            message_text = parse_message_response(msg_provider["name"], msg_raw_response)
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 08] Generating message via provider — {e}",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )

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
        except Exception as e:
            try:
                if _claimed_email_id:
                    emails.increment_email_stats(_claimed_email_id, "failed")
            except Exception:
                pass
            fail_and_notify(
                msg,
                f"[Step 09] Failed to send outreach email via SMTP — {e}",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )
        try:
            emails.increment_email_stats(_claimed_email_id, "success")
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 09] Email usage stats after successful send — {e}",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )

        print("  ")
        print("[Step 10] Marking contact message as sent...")
        try:
            contact_messages.mark_sent(
                msg_id,
                message_text,
                email_id=_claimed_email_id,
                ai_api_key_id_for_message_gen=_claimed_msg_api_key_id,
            )
        except Exception as e:
            fail_and_notify(
                msg,
                f"[Step 10] Marking contact message as sent — {e}",
                smtp_email=smtp_email,
                smtp_password=smtp_password,
                profile=profile,
                contact=contact,
                email_config=email_config,
                msg_provider=msg_provider,
                msg_api_key=msg_api_key,
            )

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
                f"<hr/><h3>Message sent</h3>"
                f"<pre style=\"background:#f5f5f5;padding:12px;border-radius:6px;font-size:13px;\">"
                f"{_html_escape(message_text)}</pre>"
            )
            if not config.NOTIFICATION_EMAIL:
                print("  -> [WARN] NOTIFICATION_EMAIL is not set, skipping confirmation email.")
            else:
                send_email(
                    config.NOTIFICATION_EMAIL,
                    confirm_subject,
                    confirm_body,
                    smtp_email,
                    smtp_password,
                    attachment_path=attachment,
                )
                print(f"  -> Confirmation sent successfully (to: {mask(config.NOTIFICATION_EMAIL, 'email')})")
        except Exception as e:
            print(f"  -> [WARN] [Step 11] Confirmation email failed (message already sent): {mask(str(e))}")
            try:
                ce, cp = _smtp_pair(smtp_email, smtp_password)
                if ce and cp and config.NOTIFICATION_EMAIL:
                    send_email(
                        config.NOTIFICATION_EMAIL,
                        "⚠️ Confirmation email failed (message was sent)",
                        f"<p>{_html_escape(e)}</p><p>Check logs; contact message status should already be <code>sent</code>.</p>",
                        ce,
                        cp,
                    )
            except Exception:
                pass

        print("---------------")
        print(f"✅ DONE — sent to {mask(contact.get('email', ''), 'email')}")

    except SystemExit:
        raise
    except Exception as e:
        try:
            if _claimed_email_id:
                emails.increment_email_stats(_claimed_email_id, "failed")
        except Exception:
            pass
        fail_and_notify(
            msg,
            f"[Workflow] Unexpected error — {e}",
            smtp_email=smtp_email,
            smtp_password=smtp_password,
            profile=profile,
            contact=contact,
            email_config=email_config,
            msg_provider=msg_provider,
            msg_api_key=msg_api_key,
        )
    finally:
        _release_claimed_resources()
        _current_msg_id = None


if __name__ == "__main__":
    main()

