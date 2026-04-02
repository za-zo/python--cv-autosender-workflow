from bson import ObjectId
from db.connection import get_db


def get_email(email_id):
    """Get an email config by ID."""
    db = get_db()
    return db.emails.find_one({"_id": ObjectId(email_id)})


def deactivate_email(email_id):
    """Deactivate an email config."""
    db = get_db()
    db.emails.update_one(
        {"_id": ObjectId(email_id)},
        {"$set": {"active": False}},
    )
