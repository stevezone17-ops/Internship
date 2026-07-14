# 🏦 Online Banking Management System

A secure and user-friendly web-based banking application developed using **Flask** and **MongoDB Atlas**. The system allows users to create accounts, manage transactions, transfer funds, monitor account activity, and securely access banking services through a modern web interface.

---

## 📌 Features

### 👤 User Management
- User Registration
- Secure Login & Logout
- Password Hashing
- Transaction PIN Authentication
- Session Management
- Profile Management

### 💰 Banking Operations
- Deposit Money
- Withdraw Money
- Transfer Funds Between Accounts
- Current Account Balance
- Transaction History
- Transaction Search & Filters
- Beneficiary Management

### 📊 Dashboard
- Account Summary
- Current Balance
- Recent Transactions
- Banking Statistics
- Interactive Charts

### 🔒 Security Features
- Password Hashing using Werkzeug
- Transaction PIN Verification
- CSRF Protection
- Session Timeout
- Login Attempt Limiting
- Secure Flask Sessions
- MongoDB Atlas Secure Connection

### 📋 Additional Features
- Customer Support Module
- Notifications
- Scheduled Transfers
- Login Activity Tracking
- Admin Dashboard
- CSV Export
- PDF Export
- Dark/Light Theme

---

# 🛠️ Tech Stack

| Layer | Technology |
|--------|------------|
| Frontend | HTML5, CSS3, JavaScript, Jinja2 |
| Backend | Flask (Python) |
| Database | MongoDB Atlas |
| Deployment | Render |
| Version Control | Git & GitHub |
| Production Server | Gunicorn |

---

# 📂 Project Structure

```
Internship/
│
├── app.py
├── requirements.txt
├── README.md
│
├── models/
│   └── db.py
│
├── routes/
│   ├── auth.py
│   ├── accounts.py
│   ├── admin.py
│   ├── beneficiaries.py
│   ├── notifications.py
│   ├── scheduled.py
│   ├── support.py
│   ├── transactions.py
│   └── main.py
│
├── services/
│
├── templates/
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
├── utils/
│
└── tests/
```

---

# ⚙️ Installation

## Clone the Repository

```bash
git clone https://github.com/stevezone17-ops/Internship.git

cd Internship
```

---

## Create Virtual Environment

Windows

```bash
python -m venv .venv

.venv\Scripts\activate
```

Linux / Mac

```bash
python3 -m venv .venv

source .venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Configure Environment Variables

Create a `.env` file or configure Render Environment Variables.

Example:

```env
MONGO_URI=your_mongodb_connection_string

FLASK_SECRET_KEY=your_secret_key

SESSION_COOKIE_SECURE=False
```

---

## Run the Application

```bash
python app.py
```

The application will run on

```
http://127.0.0.1:5000
```

---

# 🌐 Deployment

This project is deployed using **Render**.

Production Server:

```
Gunicorn
```

Database:

```
MongoDB Atlas
```

---

# 📊 Database Collections

The application uses the following MongoDB collections:

- users
- accounts
- transactions
- beneficiaries
- notifications
- scheduled_transfers
- support_queries
- login_activity

---

# 🔐 Security

The application implements:

- Password Hashing
- Transaction PIN Authentication
- Secure Sessions
- CSRF Protection
- Login Rate Limiting
- Session Expiration
- MongoDB Atlas Secure Database

---


---

# 🚀 Future Enhancements

- Email OTP Verification
- SMS Notifications
- Mobile Banking App
- AI Financial Assistant
- Loan Management
- QR Code Payments
- Budget Analysis
- Investment Dashboard
- Two-Factor Authentication (2FA)
- Biometric Authentication

---


---

# ⭐ Repository

If you found this project helpful, consider giving it a ⭐ on GitHub.

Repository:

https://github.com/stevezone17-ops/Internship
