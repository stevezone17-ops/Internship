import uuid

from utils.fraud import check_fraud
from utils.time_utils import ist_now


def create_transaction_doc(account_id, tx_type, amount, metadata=None):
    timestamp = ist_now()
    tx_tuple = (str(uuid.uuid4()), tx_type, float(amount), timestamp, metadata or {})
    tx_doc = {
        "transaction_id": tx_tuple[0],
        "account_id": account_id,
        "type": tx_tuple[1],
        "amount": tx_tuple[2],
        "timestamp": tx_tuple[3],
        "metadata": tx_tuple[4],
    }
    return tx_doc, tx_tuple


def record_transaction(transactions_col, account_id, tx_type, amount, metadata=None):
    tx_doc, tx_tuple = create_transaction_doc(account_id, tx_type, amount, metadata)
    transactions_col.insert_one(tx_doc)
    warnings = check_fraud(transactions_col, account_id, float(amount), tx_doc["timestamp"])
    return tx_doc, tx_tuple, warnings
