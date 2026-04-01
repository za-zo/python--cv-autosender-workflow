from pymongo import MongoClient
import config

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(config.MONGO_URI)
        _db = _client[config.MONGO_DB_NAME]
    return _db