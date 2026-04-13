from bson import ObjectId
from db.connection import get_db

def get_email_provider(provider_id):
    """Get an email provider by ID."""
    db = get_db()
    return db.emailproviders.find_one({"_id": ObjectId(provider_id)})
