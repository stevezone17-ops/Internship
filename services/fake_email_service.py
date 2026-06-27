from datetime import datetime

import pytz

IST = pytz.timezone("Asia/Kolkata")


def _format_amount(amount):
    return f"₹{amount:,.2f}"


def _format_time(timestamp=None):
    current_time = timestamp or datetime.now(IST)
    return current_time.strftime("%d %b %Y, %I:%M %p IST")


def _base_context(title, greeting, body, footer, accent_color, icon):
        return {
                "title": title,
                "greeting": greeting,
                "body": body,
                "footer": footer,
                "accent_color": accent_color,
                "icon": icon,
        }


def build_transfer_email(sender_name, amount, recipient_name, timestamp=None):
    amount_label = _format_amount(amount)
    date_label = _format_time(timestamp)
    message = (
        f"Hello {sender_name},\n\n"
        f"{amount_label} has been transferred successfully.\n\n"
        "Recipient:\n"
        f"{recipient_name}\n\n"
        "Transaction Type:\n"
        "Transfer\n\n"
        "Date:\n"
        f"{date_label}\n\n"
        "If this was not you,\n"
        "please contact support immediately."
    )
    context = _base_context(
        "Transfer Successful",
        f"Hello {sender_name},",
        f"{amount_label} has been transferred successfully.",
        "If this was not you, contact support immediately.",
        "#3b82f6",
        "📤",
    )
    context.update(
        {
            "amount": amount_label,
            "date": date_label,
            "counterpart_label": "Recipient",
            "counterpart_name": recipient_name,
        }
    )
    return "Transfer Successful", message, "emails/transfer_email.html", context


def build_transfer_received_email(receiver_name, amount, sender_name, timestamp=None):
    amount_label = _format_amount(amount)
    date_label = _format_time(timestamp)
    message = (
        f"Hello {receiver_name},\n\n"
        f"{amount_label} has been received successfully.\n\n"
        "Sender:\n"
        f"{sender_name}\n\n"
        "Transaction Type:\n"
        "Transfer\n\n"
        "Date:\n"
        f"{date_label}\n\n"
        "If this was not you,\n"
        "please contact support immediately."
    )
    context = _base_context(
        "Transfer Successful",
        f"Hello {receiver_name},",
        f"{amount_label} has been received successfully.",
        "If this was not you, contact support immediately.",
        "#3b82f6",
        "📥",
    )
    context.update(
        {
            "amount": amount_label,
            "date": date_label,
            "counterpart_label": "Sender",
            "counterpart_name": sender_name,
        }
    )
    return "Transfer Successful", message, "emails/transfer_email.html", context


def build_withdraw_email(user_name, amount, remaining_balance, timestamp=None):
    amount_label = _format_amount(amount)
    balance_label = _format_amount(remaining_balance)
    date_label = _format_time(timestamp)
    message = (
        f"Hello {user_name},\n\n"
        f"{amount_label} has been withdrawn successfully.\n\n"
        "Remaining Balance:\n"
        f"{balance_label}\n\n"
        "Date:\n"
        f"{date_label}\n\n"
        "Thank you for banking with us."
    )
    context = _base_context(
        "Withdrawal Successful",
        f"Hello {user_name},",
        f"{amount_label} has been withdrawn successfully.",
        "Thank you for banking with us.",
        "#ef4444",
        "➖",
    )
    context.update({"amount": amount_label, "balance": balance_label, "date": date_label})
    return "Withdrawal Successful", message, "emails/withdraw_email.html", context

def build_deposit_email(user_name, amount, remaining_balance, timestamp=None):
    amount_label = _format_amount(amount)
    balance_label = _format_amount(remaining_balance)
    date_label = _format_time(timestamp)
    message = (
        f"Hello {user_name},\n\n"
        f"{amount_label} has been deposited successfully.\n\n"
        "Available Balance:\n"
        f"{balance_label}\n\n"
        "Date:\n"
        f"{date_label}\n\n"
        "Thank you for banking with us."
    )
    context = _base_context(
        "Deposit Successful",
        f"Hello {user_name},",
        f"{amount_label} has been deposited successfully.",
        "Thank you for banking with us.",
        "#22c55e",
        "➕",
    )
    context.update({"amount": amount_label, "balance": balance_label, "date": date_label})
    return "Deposit Successful", message, "emails/deposit_email.html", context


def send_fake_email(to, subject, message):
    current_time = _format_time()
    print("\n")
    print("=" * 60)
    print("📧 BANK EMAIL NOTIFICATION")
    print("=" * 60)
    print(f"To: {to}")
    print(f"Subject: {subject}")
    print(f"Time: {current_time}")
    print("-" * 60)
    print(message)
    print("=" * 60)
    print("\n")


def send_deposit_email(to, subject, message):
    send_fake_email(to, subject, message)
