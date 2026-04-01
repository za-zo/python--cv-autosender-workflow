from db.connection import get_db

def get_profile():
    """Get the first profile (single-user system)."""
    db = get_db()
    return db.profiles.find_one()