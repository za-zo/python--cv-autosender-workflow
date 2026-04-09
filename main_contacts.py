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
            raise RuntimeError("Profile not found (db.profiles.find_one returned None)")

        print("  ")
        print("[Step 03] Reading contact...")
        contact = contacts.get_contact(msg["contactId"])
        if not contact:
            raise RuntimeError(f"Contact not found for contactId={msg.get('contactId')}")

        print("  ")
        print("[Step 04] Claiming email config...")
        raw_email_id = msg.get("emailId")
        if raw_email_id:
            email_config = emails.claim_email_by_id(raw_email_id)
        else:
            email_config = emails.claim_available_email()
        if not email_config:
            raise RuntimeError("No available email config (active=true and not in_use)")
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
            raise RuntimeError("No available message API key (active=true and not in_use)")
        _claimed_msg_api_key_id = str(msg_api_key["_id"])
        print(f"  -> Message API key claimed: {mask(msg_api_key.get('name', ''))} | ID: {mask(_claimed_msg_api_key_id)}")

        print("  ")
        print("[Step 06] Reading message API key provider...")
        msg_provider = providers.get_provider(msg_api_key["provider"])
        if not msg_provider:
            raise RuntimeError("Message provider not found for message API key")

        print("  ")
        print("[Step 07] Building outreach prompt...")
        msg_system, msg_user, lang = build_contact_message_prompt(profile, contact, msg)
        print(f"  -> Language: {mask(lang)} | Prompt: {len(msg_user)} chars")

        print("  ")
        print(f"[Step 08] Generating message via {mask(msg_provider['name'])}...")
        msg_provider_module = get_provider_module(msg_provider["name"])
        msg_raw_response = msg_provider_module.call(
            msg_api_key["apiKey"],
            msg_system,
            msg_user,
            model_name=msg_provider.get("model_name"),
        )
        message_text = parse_message_response(msg_provider["name"], msg_raw_response)

        print("  ")
        print(f"[Step 09] Sending outreach email to {mask(contact.get('email', ''), 'email')}...")
        subject = f"{profile.get('firstName', '')} {profile.get('lastName', '')} — Introduction"
        attachment = _cv_attachment_path(lang)
        send_email(
            contact["email"],
            subject,
            f"<pre>{message_text}</pre>",
            smtp_email,
            smtp_password,
            attachment_path=attachment,
        )
        emails.increment_email_stats(_claimed_email_id, "success")

        print("  ")
        print("[Step 10] Marking contact message as sent...")
        contact_messages.mark_sent(
            msg_id,
            message_text,
            email_id=_claimed_email_id,
            ai_api_key_id_for_message_gen=_claimed_msg_api_key_id,
        )

        print("---------------")
        print(f"✅ DONE — sent to {mask(contact.get('email', ''), 'email')}")

    except Exception as e:
        try:
            if _claimed_email_id:
                emails.increment_email_stats(_claimed_email_id, "failed")
        except Exception:
            pass
        try:
            contact_messages.mark_failed(msg_id, str(e))
        except Exception:
            pass
        print(f"  -> [FAIL] {mask(str(e))}")
        sys.exit(1)
    finally:
        _release_claimed_resources()
        _current_msg_id = None


if __name__ == "__main__":
    main()

