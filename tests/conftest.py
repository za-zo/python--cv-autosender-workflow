from db.connection import get_db


def get_test_api_key(provider_name):
    """Get an active API key for the given provider name from MongoDB."""
    db = get_db()
    provider = db.providers.find_one(
        {"name": {"$regex": provider_name, "$options": "i"}}
    )
    if not provider:
        return None, None
    api_key = db.aiapikeys.find_one(
        {"provider": provider["_id"], "active": True}
    )
    return provider, api_key
