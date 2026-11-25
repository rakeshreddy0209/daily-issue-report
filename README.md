# Cautio daily issue report automation

This GitHub Actions workflow reads the existing public, view-only Google Sheets export. It does not sign in to or change the tracker. At 9:00 PM India time, it selects issue timestamps from the previous 9:00 AM inclusive through the current 9:00 AM exclusive, produces one Cautio-branded HTML email, and sends it to one configured report recipient.

## Before enabling the schedule

The report contains rows for multiple clients. Configure `REPORT_TO` as one internal recipient authorized to see the combined report. Do not put all client addresses in this setting. A consolidated report sent to every client would reveal other clients' issue details. If client delivery is required, use a separate, client-filtered workflow and an approved client-to-address mapping.

Add these repository Actions secrets under **Settings → Secrets and variables → Actions**:

- `REPORT_TO` — one approved internal report recipient
- `MAIL_FROM` — sender address authorized by the SMTP account
- `MAIL_HOST` — SMTP server hostname
- `MAIL_PORT` — SMTP TLS submission port (commonly 587)
- `MAIL_USERNAME` — SMTP account username
- `MAIL_PASSWORD` — SMTP app password or SMTP credential

The sender account must be authorized to send from the address in `MAIL_FROM`.

The sheet CSV link is embedded in the workflow because the sheet is already link-viewable. The destination repository is currently public, so anyone can see the export link and read the sheet. The workflow does not commit or publish downloaded issue rows or report output. If public read access to the sheet is not intended, make the sheet private and use a read-only service account/token flow before enabling this automation.

## Timing

The workflow runs at 9:00 PM Asia/Kolkata. GitHub notes that scheduled runs can be delayed during high load. Scheduled Actions in public repositories may also be disabled after 60 days without repository activity. A failed run appears in the repository's Actions tab and GitHub's configured failure notifications.

`workflow_dispatch` allows a manual run after the secrets are configured. The script refuses to email if the source timestamps do not match the expected format or email settings are incomplete.
