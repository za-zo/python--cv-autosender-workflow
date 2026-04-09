from bson import ObjectId

from db.connection import get_db


def _oid(value):
    return value if isinstance(value, ObjectId) else ObjectId(str(value))


def get_contact(contact_id):
    """Get a contact by ID."""
    db = get_db()
    return db.contacts.find_one({"_id": _oid(contact_id)})

