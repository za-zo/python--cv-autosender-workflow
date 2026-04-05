from datetime import datetime, timezone
from bson import ObjectId
from db.connection import get_db

def claim_job():
    """Atomically claim one active, not-in-use job."""
    db = get_db()
    return db.jobs.find_one_and_update(
        {
            "active": True,
            "$or": [{"in_use": False}, {"in_use": {"$exists": False}}],
        },
        {"$set": {"in_use": True}},
        sort=[("createdAt", 1)],
    )

def mark_sent(
    job_id,
    generated_message,
    *,
    email_id=None,
    cv_api_key_id=None,
    msg_api_key_id=None,
):
    """Mark job as successfully sent; optionally persist which email/API keys were used."""
    db = get_db()
    fields = {
        "active": False,
        "in_use": False,
        "status": "sent",
        "failed_reason": None,
        "sentAt": datetime.now(timezone.utc),
        "generatedMessage": generated_message,
    }
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": fields},
    )


def mark_failed(job_id, reason):
    """Mark job as failed with a clear reason."""
    db = get_db()
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {
            "$set": {
                "active": False,
                "in_use": False,
                "status": "failed",
                "failed_reason": reason,
            }
        },
    )

def release_job(job_id):
    """Release a job back to the pool (in_use=False, keep active)."""
    db = get_db()
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"in_use": False}},
    )

def has_active_jobs():
    """Check if there are any active jobs remaining."""
    db = get_db()
    return db.jobs.count_documents({"active": True}) > 0