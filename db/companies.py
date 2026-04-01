from bson import ObjectId
from db.connection import get_db

def get_company(company_id):
    """Get a company by ID."""
    db = get_db()
    return db.companies.find_one({"_id": ObjectId(company_id)})