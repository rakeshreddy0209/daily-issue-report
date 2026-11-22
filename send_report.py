#!/usr/bin/env python3
"""
Daily Issue Report — Full Dashboard Email (No Links, All Data Inline)
Fetches Google Sheet as CSV, filters 9AM-9AM window, emails dashboard.
"""

import os
import csv
import io
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone


# ═══════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

SHEET_ID = "1DzW-6Q7hTNn2hSJbEHOkSrbalOmbDIftdjw4I_PhEdA"
GID = "0"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

DATE_COLUMN = "Timestamp Issues Raised"
RECIPIENT_EMAIL = "mohammad.yunus@cautio.in"

EMAIL_COLUMNS = [
    "Issue Id",
    "Clients",
    "Vehicle Number",
    "Timestamp Issues Raised",
    "Raised by",
    "Raised via [Forum]",
    "Sub-request",
    "Issue Details",
    "Incident Type",
    "Remarks (Incident Details)",
    "Assigned To",
    "Location",
    "Resolved Y/N",
]

IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════════════════════════════════
#  FETCH & FILTER
# ═══════════════════════════════════════════════════════════════════

def fetch_sheet_data():
    print(f"   Downloading from: {CSV_URL}")
    response = requests.get(CSV_URL, timeout=30)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    return [row for row in reader]


def parse_date(date_str):
    date_str = str(date_str).strip()
    if not date_str:
        return None
    for fmt in [
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    ]:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def filter_issues(records):
    now_ist = datetime.now(IST)
    today_9am = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    if now_ist < today_9am:
        today_9am -= timedelta(days=1)
    yesterday_9am = today_9am - timedelta(days=1)

    filtered = []
    for row in records:
        dt = parse_date(row.get(DATE_COLUMN, ""))
        if dt and yesterday_9am <= dt < today_9am:
            filtered.append(row)

    return filtered, yesterday_9am, today_9am


# ═══════════════════════════════════════════════════════════════════
#  BUILD DASHBOARD EMAIL
# ═══════════════════════════════════════════════════════════════════

def build_email(issues, start_time, end_time):
    period = (
        f"{start_time.strftime('%d %b %Y, %I:%M %p')} &rarr; "
        f"{end_time.strftime('%d %b %Y, %I:%M %p')} IST"
    )
    report_date = end_time.strftime("%d %b %Y")

    if not issues:
        return f"""
<html><body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:750px;margin:20px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:28px 32px;color:white;">
    <h1 style="margin:0;font-size:22px;font-weight:600;">&#128203; Daily Issue Report</h1>
    <p style="margin:6px 0 0;opacity:0.8;font-size:14px;">Cautio &middot; {report_date}</p>
  </div>
  <div style="padding:32px;">
    <p style="color:#666;font-size:13px;"><strong>Period:</strong> {period}</p>
    <div style="background:#e8f5e9;padding:24px;border-radius:8px;text-align:center;margin:20px 0;">
      <div style="font-size:36px;">&#9989;</div>
      <p style="color:#2e7d32;font-size:17px;margin:10px 0 0;font-weight:600;">No new issues were raised during this period.</p>
    </div>
  </div>
  <div style="background:#f8f9fa;padding:14px 32px;text-align:center;">
    <p style="color:#aaa;font-size:11px;margin:0;">Automated report &middot; Issue Tracker &middot; Cautio</p>
  </div>
</div></body></html>"""

    total = len(issues)
    resolved = sum(1 for i in issues if str(i.get("Resolved Y/N", "")).strip().upper() in ("YES", "Y"))
    unresolved = total - resolved
    clients = set(str(i.get("Clients", "")).strip() for i in issues if str(i.get("Clients", "")).strip())
    res_rate = round((resolved / total) * 100) if total else 0

    def stat_card(value, label, color, bg):
        return f'''<td style="padding:6px;">
          <div style="background:{bg};border-radius:8px;padding:14px 8px;text-align:center;border-left:4px solid {color};">
            <div style="font-size:26px;font-weight:700;color:{color};">{value}</div>
            <div style="font-size:11px;color:#666;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;">{label}</div>
          </div></td>'''

    stats_row = (
        stat_card(total, "Total", "#2980b9", "#ebf5fb")
        + stat_card(unresolved, "Open", "#e74c3c", "#fdedec")
        + stat_card(resolved, "Resolved", "#27ae60", "#e8f8f5")
        + stat_card(len(clients), "Clients", "#8e44ad", "#f4ecf7")
        + stat_card(f"{res_rate}%", "Res. Rate", "#f39c12", "#fef9e7")
    )

    issue_rows = ""
    for idx, iss in enumerate(issues, 1):
        bg = "#ffffff" if idx % 2 == 1 else "#f8fafc"
        resolved_yn = str(iss.get("Resolved Y/N", "")).strip().upper()
        if resolved_yn in ("YES", "Y"):
            status_badge = '<span style="background:#27ae60;color:white;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">RESOLVED</span>'
            row_border = "#27ae60"
        else:
            status_badge = '<span style="background:#e74c3c;color:white;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;">OPEN</span>'
            row_border = "#e74c3c"

        issue_id = str(iss.get("Issue Id", "")).strip()
        client = str(iss.get("Clients", "")).strip()
        vehicle = str(iss.get("Vehicle Number", "")).strip()
        timestamp = str(iss.get(DATE_COLUMN, "")).strip()
        raised_by = str(iss.get("Raised by", "")).strip()
        raised_via = str(iss.get("Raised via [Forum]", "")).strip()
        sub_request = str(iss.get("Sub-request", "")).strip()
        details = str(iss.get("Issue Details", "")).strip()
        incident_type = str(iss.get("Incident Type", "")).strip()
        remarks = str(iss.get("Remarks (Incident Details)", "")).strip()
        assigned_to = str(iss.get("Assigned To", "")).strip()
        location = str(iss.get("Location", "")).strip()
        jira = str(iss.get("JIRA ticket ID", "")).strip()
        footage_reason = str(iss.get("Footage Non-Delivery Reason", "")).strip()

        inc_colors = {
            "normal": ("#3498db", "#ebf5fb"), "accident": ("#e74c3c", "#fdedec"),
            "critical": ("#e74c3c", "#fdedec"), "high": ("#e67e22", "#fef5e7"),
        }
        inc_lower = incident_type.lower() if incident_type else ""
        ic, ibg = inc_colors.get(inc_lower, ("#7f8c8d", "#f2f3f4"))
        incident_badge = f'<span style="background:{ibg};color:{ic};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">{incident_type}</span>' if incident_type else ""

        detail_parts = []
        if sub_request:
            detail_parts.append(f"<strong>Request:</strong> {sub_request}")
        if details:
            detail_parts.append(f"<strong>Details:</strong> {details}")
        if remarks:
            detail_parts.append(f"<strong>Remarks:</strong> {remarks}")
        if footage_reason:
            detail_parts.append(f"<strong>Footage:</strong> {footage_reason}")
        if location:
            detail_parts.append(f"&#128205; {location}")
        detail_html = "<br>".join(detail_parts)

        assigned_html = f'<div style="font-size:11px;color:#888;margin-top:6px;">&rarr; {assigned_to}</div>' if assigned_to else ""
        jira_html = f'<div style="font-size:10px;color:#aaa;margin-top:2px;">JIRA: {jira}</div>' if jira else ""

        issue_rows += f'''
        <tr style="background:{bg};border-left:4px solid {row_border};">
          <td style="padding:12px 10px;border-bottom:1px solid #eef1f5;text-align:center;font-weight:700;color:#555;font-size:13px;vertical-align:top;">{idx}</td>
          <td style="padding:12px 10px;border-bottom:1px solid #eef1f5;vertical-align:top;">
            <div style="font-weight:700;color:#2c3e50;font-size:14px;">{issue_id}</div>
            <div style="margin-top:4px;">{incident_badge}</div>
          </td>
          <td style="padding:12px 10px;border-bottom:1px solid #eef1f5;vertical-align:top;">
            <div style="font-weight:600;color:#2c3e50;font-size:13px;">{client}</div>
            <div style="color:#888;font-size:12px;margin-top:2px;">&#128663; {vehicle}</div>
          </td>
          <td style="padding:12px 10px;border-bottom:1px solid #eef1f5;vertical-align:top;">
            <div style="font-size:12px;color:#555;">&#128100; {raised_by}</div>
            <div style="font-size:11px;color:#999;margin-top:2px;">via {raised_via}</div>
            <div style="font-size:11px;color:#999;margin-top:2px;">&#128336; {timestamp}</div>
          </td>
          <td style="padding:12px 10px;border-bottom:1px solid #eef1f5;vertical-align:top;font-size:12px;color:#444;line-height:1.6;">{detail_html}</td>
          <td style="padding:12px 10px;border-bottom:1px solid #eef1f5;vertical-align:top;text-align:center;">
            {status_badge}{assigned_html}{jira_html}
          </td>
        </tr>'''

    return f"""
<html><body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:900px;margin:20px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:28px 32px;color:white;">
    <h1 style="margin:0;font-size:22px;font-weight:600;">&#128203; Daily Issue Report</h1>
    <p style="margin:6px 0 0;opacity:0.8;font-size:14px;">Cautio &middot; {report_date}</p>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#666;font-size:13px;margin:0 0 16px;"><strong>Reporting Period:</strong> {period}</p>
    <table style="width:100%;border-collapse:separate;border-spacing:6px;" cellpadding="0" cellspacing="0">
      <tr>{stats_row}</tr>
    </table>
    <div style="background:#f8f9fa;padding:10px 16px;border-radius:6px;margin:16px 0 20px;font-size:12px;color:#555;">
      <strong>Clients:</strong> {", ".join(sorted(clients))}
    </div>
    <table style="width:100%;border-collapse:collapse;" cellpadding="0" cellspacing="0">
      <thead>
        <tr style="background:#1a1a2e;">
          <th style="padding:12px 10px;color:white;font-size:11px;text-align:center;width:35px;">#</th>
          <th style="padding:12px 10px;color:white;font-size:11px;text-align:left;width:100px;">ISSUE ID</th>
          <th style="padding:12px 10px;color:white;font-size:11px;text-align:left;width:130px;">CLIENT / VEHICLE</th>
          <th style="padding:12px 10px;color:white;font-size:11px;text-align:left;width:120px;">RAISED BY</th>
          <th style="padding:12px 10px;color:white;font-size:11px;text-align:left;">DETAILS</th>
          <th style="padding:12px 10px;color:white;font-size:11px;text-align:center;width:100px;">STATUS</th>
        </tr>
      </thead>
      <tbody>{issue_rows}</tbody>
    </table>
  </div>
  <div style="background:#f8f9fa;padding:14px 28px;text-align:center;border-top:1px solid #eee;">
    <p style="color:#aaa;font-size:11px;margin:0;">Automated report &middot; Issue Tracker &middot; Cautio</p>
  </div>
</div></body></html>"""


# ═══════════════════════════════════════════════════════════════════
#  SEND EMAIL
# ═══════════════════════════════════════════════════════════════════

def send_email(html_content, issue_count, end_time):
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    date_str = end_time.strftime("%d %b %Y")
    subject = f"Daily Issue Report - {date_str} | {issue_count} Issue(s)"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Cautio Issue Tracker <{sender}>"
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [RECIPIENT_EMAIL], msg.as_string())

    print(f"Email sent to {RECIPIENT_EMAIL}")


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    print("Fetching data from Google Sheet (CSV export)...")
    records = fetch_sheet_data()
    print(f"   Total rows in sheet: {len(records)}")

    print("Filtering issues for 9AM to 9AM window...")
    issues, start_time, end_time = filter_issues(records)
    print(f"   Issues in window: {len(issues)}")

    print("Building and sending email...")
    html = build_email(issues, start_time, end_time)
    send_email(html, len(issues), end_time)

    print("Done!")


if __name__ == "__main__":
    main()
