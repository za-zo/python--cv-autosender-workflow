from datetime import datetime, timezone
import time

from bson import ObjectId

from db.connection import get_db


_POOL_FILTER = {
    "active": True,
    "status": "pending",
    "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
}


def _oid(value):
    return value if isinstance(value, ObjectId) else ObjectId(str(value))


def claim_contact_message():
    """Atomically claim one active, pending, not-in-use contact message."""
    db = get_db()
    return db.contactmessages.find_one_and_update(
        _POOL_FILTER,
        {"$set": {"in_use": True}},
        sort=[("createdAt", 1)],
    )


def claim_contact_message_by_id(contact_message_id):
    """Atomically claim a specific contact message by ID."""
    db = get_db()
    return db.contactmessages.find_one_and_update(
        {
            "_id": _oid(contact_message_id),
            "active": True,
            "status": "pending",
            "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
        },
        {"$set": {"in_use": True}},
    )


def release_contact_message(contact_message_id):
    """Release a claimed contact message back to the pool (in_use=False)."""
    db = get_db()
    db.contactmessages.update_one(
        {"_id": _oid(contact_message_id)},
        {"$set": {"in_use": False}},
    )


def mark_sent(
    contact_message_id,
    generated_content,
    *,
    email_id=None,
    ai_api_key_id_for_message_gen=None,
    gmail_message_id=None,
):
    """Mark contact message as sent; persist generatedContent and optional metadata."""
    db = get_db()
    fields = {
        "active": False,
        "in_use": False,
        "status": "sent",
        "failed_reason": None,
        "sentAt": datetime.now(timezone.utc),
        "generatedContent": generated_content,
    }
    if gmail_message_id:
        fields["gmailMessageId"] = str(gmail_message_id)
    db.contactmessages.update_one({"_id": _oid(contact_message_id)}, {"$set": fields})


def mark_failed(contact_message_id, reason):
    """Mark contact message as failed with reason."""
    db = get_db()
    db.contactmessages.update_one(
        {"_id": _oid(contact_message_id)},
        {
            "$set": {
                "active": False,
                "in_use": False,
                "status": "failed",
                "failed_reason": reason,
            }
        },
    )


def has_active_contact_messages():
    """Check if any pending contact messages remain."""
    db = get_db()
    return db.contactmessages.count_documents({"active": True, "status": "pending"}) > 0


def claim_available_contact_message(max_attempts=8):
    """Claim an available contact message from pool (retry to reduce race conditions)."""
    db = get_db()
    for _ in range(max_attempts):
        doc = db.contactmessages.find_one_and_update(
            _POOL_FILTER,
            {"$set": {"in_use": True}},
            sort=[("createdAt", 1)],
        )
        if doc:
            return doc
        time.sleep(0.02)
    return None

