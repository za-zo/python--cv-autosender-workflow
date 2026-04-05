import time
from bson import ObjectId
from db.connection import get_db

_POOL_FILTER = {
    "active": True,
    "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
}


def _oid(value):
    return value if isinstance(value, ObjectId) else ObjectId(str(value))


def get_email_by_id(email_id):
    """Get an email config by ID (plain find, no claim)."""
    db = get_db()
    return db.emails.find_one({"_id": _oid(email_id)})


def get_email(email_id):
    """Get an email config by ID (alias)."""
    return get_email_by_id(email_id)


def claim_email_by_id(email_id):
    """Atomically claim one email: active, not in_use -> set in_use True."""
    db = get_db()
    return db.emails.find_one_and_update(
        {
            "_id": _oid(email_id),
            "active": True,
            "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
        },
        {"$set": {"in_use": True}},
    )


def claim_random_email(max_attempts=8):
    """Claim a random available email from the pool (sample + atomic update)."""
    db = get_db()
    for _ in range(max_attempts):
        sample = list(
            db.emails.aggregate(
                [
                    {"$match": _POOL_FILTER},
                    {"$sample": {"size": 1}},
                ]
            )
        )
        if not sample:
            return None
        oid = sample[0]["_id"]
        doc = db.emails.find_one_and_update(
            {
                "_id": oid,
                "active": True,
                "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
            },
            {"$set": {"in_use": True}},
        )
        if doc:
            return doc
        time.sleep(0.02)
    return None


def release_email_in_use(email_id):
    """Release in_use flag on an email document."""
    db = get_db()
    db.emails.update_one(
        {"_id": _oid(email_id)},
        {"$set": {"in_use": False}},
    )


def increment_email_stats(email_id, outcome):
    """Increment usage counters. outcome is 'success' or 'failed'."""
    if outcome not in ("success", "failed"):
        raise ValueError("outcome must be 'success' or 'failed'")
    db = get_db()
    inc = {"usage_count": 1, "usageCount": 1}
    if outcome == "success":
        inc["successUsageCount"] = 1
    else:
        inc["failedUsageCount"] = 1
    db.emails.update_one({"_id": _oid(email_id)}, {"$inc": inc})


def deactivate_email(email_id):
    """Deactivate an email config and clear in_use."""
    db = get_db()
    db.emails.update_one(
        {"_id": _oid(email_id)},
        {"$set": {"active": False, "in_use": False}},
    )
