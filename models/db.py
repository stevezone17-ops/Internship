import os
from pymongo import MongoClient

try:
    import mongomock
except ImportError:
    mongomock = None

_DB_CACHE = None

def get_db():
    global _DB_CACHE
    if _DB_CACHE is not None:
        return _DB_CACHE

    use_mock = os.environ.get("USE_MOCK_DB") == "1"
    if use_mock and mongomock:
        _DB_CACHE = mongomock.MongoClient().db
    else:
        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/bank_simulator")
        client = MongoClient(mongo_uri)
        _DB_CACHE = client.get_default_database() or client["bank_simulator"]
    
    _ensure_collections(_DB_CACHE)
    return _DB_CACHE

def _ensure_collections(db):
    required = [
        "accounts",
        "transactions",
        "users",
        "notifications",
        "support_queries",
        "beneficiaries",
        "login_activity",
        "scheduled_transfers",
    ]
    existing = db.list_collection_names()
    for coll in required:
        if coll not in existing:
            db.create_collection(coll)

def get_collections():
    db = get_db()
    return {
        "accounts": db["accounts"],
        "transactions": db["transactions"],
        "users": db["users"],
        "notifications": db["notifications"],
        "support_queries": db["support_queries"],
        "beneficiaries": db["beneficiaries"],
        "login_activity": db["login_activity"],
        "scheduled_transfers": db["scheduled_transfers"],
    }
