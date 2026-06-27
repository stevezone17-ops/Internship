from bson import ObjectId
from utils.time_utils import ist_now, format_ist


def list_beneficiaries(beneficiaries_col, user_id):
    try:
        uid = ObjectId(user_id)
    except Exception:
        return []
    cursor = beneficiaries_col.find({"user_id": uid}).sort("created_at", -1)
    results = []
    for b in cursor:
        created_at = b.get("created_at") or b.get("_id").generation_time
        results.append({
            "id": str(b.get("_id")),
            "name": b.get("name"),
            "email": b.get("email"),
            "nickname": b.get("nickname"),
            "created_at": created_at.isoformat() if created_at else None,
            "created_at_display": format_ist(created_at) if created_at else None,
        })
    return results


def add_beneficiary(beneficiaries_col, user_id, name, email, nickname=None):
    try:
        uid = ObjectId(user_id)
    except Exception:
        return None, "Invalid user id"

    # prevent duplicates per user
    existing = beneficiaries_col.find_one({"user_id": uid, "email": email.lower()})
    if existing:
        return None, "Beneficiary already exists." 

    doc = {
        "user_id": uid,
        "name": name,
        "email": email.lower(),
        "nickname": (nickname or "").strip() or None,
        "created_at": ist_now(),
    }
    result = beneficiaries_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    doc["id"] = str(result.inserted_id)
    return doc, None


def delete_beneficiary(beneficiaries_col, user_id, beneficiary_id):
    try:
        uid = ObjectId(user_id)
    except Exception:
        return False, "Invalid user id"
    try:
        bid = ObjectId(beneficiary_id)
    except Exception:
        return False, "Invalid beneficiary id"

    res = beneficiaries_col.delete_one({"_id": bid, "user_id": uid})
    if res.deleted_count == 0:
        return False, "Beneficiary not found or not owned by user"
    return True, None
