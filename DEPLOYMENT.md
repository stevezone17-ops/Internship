# Deployment Checklist

## Environment Variables

- `MONGO_URI`: MongoDB connection string
- `USE_MOCK_DB=1`: local development and tests only
- `ADMIN_EMAIL`: optional email to auto-recognize an admin account
- `FLASK_ENV`: `development` or `production`
- `SECRET_KEY`: replace the default Flask secret before production
- `SCHEDULED_TRANSFER_TOKEN`: optional shared secret for the scheduled-transfer runner

## Database

- Run the created-at backfill script:

```bash
python scripts/backfill_created_at.py
```

- Verify these collections exist:
  - `users`
  - `accounts`
  - `transactions`
  - `notifications`
  - `support_queries`
  - `beneficiaries`
  - `login_activity`
  - `scheduled_transfers`

## Scheduled Jobs

- Run scheduled transfer processing on a cron-like schedule:

```bash
curl -X POST http://localhost:5000/api/scheduled-transfers/run
```

Use Windows Task Scheduler or a cron job in production to call `POST /api/scheduled-transfers/run` at a fixed interval.
If `SCHEDULED_TRANSFER_TOKEN` is set, include it as `X-Scheduler-Token`.

## Security Checks

- Confirm password and PIN lock thresholds are acceptable for the deployment environment.
- Replace the default secret key before production.
- Set `SESSION_COOKIE_SECURE=True` behind HTTPS.

## Verification

- Log in and confirm the dashboard loads.
- Test a transfer with a wrong PIN to confirm lockout behavior.
- Open the admin dashboard with an admin account and reply to a support ticket.
- Check that login activity appears on the profile page.
