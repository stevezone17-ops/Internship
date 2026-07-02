from datetime import timedelta

def check_fraud(transactions_col, account_id, amount, timestamp):
    warnings = []
    if amount > 10000:
        warnings.append("High-value transaction flagged (> ₹10,000).")

    # DB-based frequency check
    window_start = timestamp - timedelta(minutes=1)
    recent_count = transactions_col.count_documents({
        "account_id": account_id,
        "timestamp": {"$gte": window_start}
    })

    if recent_count > 4:
        warnings.append("High-frequency activity detected (more than 3 in 1 minute).")

    return warnings
