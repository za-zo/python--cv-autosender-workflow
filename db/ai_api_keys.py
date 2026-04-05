import time
from bson import ObjectId
from db.connection import get_db

_POOL_FILTER = {
    "active": True,
    "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
}


def _oid(value):
    return value if isinstance(value, ObjectId) else ObjectId(str(value))


def get_api_key_by_id(key_id):
    """Get an API key by ID (plain find, no claim)."""
    db = get_db()
    return db.aiapikeys.find_one({"_id": _oid(key_id)})


def get_api_key(key_id):
    """Get an API key by ID (alias)."""
    return get_api_key_by_id(key_id)


def claim_api_key_by_id(key_id):
    """Atomically claim one API key: active, not in_use -> set in_use True."""
    db = get_db()
    return db.aiapikeys.find_one_and_update(
        {
            "_id": _oid(key_id),
            "active": True,
            "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
        },
        {"$set": {"in_use": True}},
    )


def claim_available_api_key(max_attempts=8):
    """Claim an available API key from the pool, prioritized by least usageCount."""
    db = get_db()
    for _ in range(max_attempts):
        candidates = list(
            db.aiapikeys.aggregate(
                [
                    {"$match": _POOL_FILTER},
                    {"$sort": {"usageCount": 1}},
                    {"$limit": 1},
                ]
            )
        )
        if not candidates:
            return None

        oid = candidates[0]["_id"]
        doc = db.aiapikeys.find_one_and_update(
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


def release_api_key_in_use(key_id):
    """Release in_use flag on an API key document."""
    db = get_db()
    db.aiapikeys.update_one(
        {"_id": _oid(key_id)},
        {"$set": {"in_use": False}},
    )


def increment_api_key_stats(key_id, outcome):
    """Increment usage counters. outcome is 'success' or 'failed'."""
    if outcome not in ("success", "failed"):
        raise ValueError("outcome must be 'success' or 'failed'")
    db = get_db()
    inc = {"usageCount": 1}
    if outcome == "success":
        inc["successUsageCount"] = 1
    else:
        inc["failedUsageCount"] = 1
    db.aiapikeys.update_one({"_id": _oid(key_id)}, {"$inc": inc})


def deactivate_api_key(key_id):
    """Deactivate an API key and clear in_use."""
    db = get_db()
    db.aiapikeys.update_one(
        {"_id": _oid(key_id)},
        {"$set": {"active": False, "in_use": False}},
    )
