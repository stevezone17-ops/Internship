"""Backfill missing created_at fields for legacy documents.

Usage:
    python scripts/backfill_created_at.py

The script is safe to run multiple times. It only updates documents that
are missing created_at and uses each document's ObjectId generation time.
"""

from models.db import get_db


COLLECTIONS = ["users", "accounts", "transactions", "notifications", "support_queries"]


def backfill_collection(collection):
    updated = 0
    query = {"$or": [{"created_at": {"$exists": False}}, {"created_at": None}]}
    for doc in collection.find(query):
        created_at = doc["_id"].generation_time
        collection.update_one({"_id": doc["_id"]}, {"$set": {"created_at": created_at}})
        updated += 1
    return updated


def main():
    db = get_db()
    totals = {}
    for name in COLLECTIONS:
        totals[name] = backfill_collection(db[name])

    for name, count in totals.items():
        print(f"{name}: backfilled {count}")


if __name__ == "__main__":
    main()