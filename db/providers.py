from bson import ObjectId
from db.connection import get_db

def get_provider(provider_id):
    """Get a provider by ID."""
    db = get_db()
    return db.providers.find_one({"_id": ObjectId(provider_id)})