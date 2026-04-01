from bson import ObjectId
from db.connection import get_db

def get_api_key(key_id):
    """Get an API key by ID."""
    db = get_db()
    return db.aiapikeys.find_one({"_id": ObjectId(key_id)})

def deactivate_api_key(key_id):
    """Deactivate an API key."""
    db = get_db()
    db.aiapikeys.update_one(
        {"_id": ObjectId(key_id)},
        {"$set": {"active": False}},
    )