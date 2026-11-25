import csv
import datetime as dt
import html
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = Path(os.environ.get("ISSUES_CSV", "issues.csv"))
OUTPUT = Path(os.environ.get("REPORT_HTML", "daily-report.html"))
TZ = ZoneInfo("Asia/Kolkata")
now = dt.datetime.now(TZ)
END = now.replace(hour=9, minute=0, second=0, microsecond=0)
if now < END:
    END -= dt.timedelta(days=1)
START = END - dt.timedelta(days=1)

def esc(value):
    return html.escape((value or "").replace("\r", " ").replace("\n", " ").strip())

def parse_timestamp(value, row_number):
    raw = (value or "").replace("\u00a0", " ").strip()
    if not raw:
        return None, False
    formats = (
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M",
        "%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y, %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
    )
    for fmt in formats:
        try:
            return dt.datetime.strptime(raw, fmt).replace(tzinfo=TZ), True
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.time() == dt.time.min and len(raw) <= 10:
            return parsed.replace(tzinfo=TZ), False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ)
        else:
            parsed = parsed.astimezone(TZ)
        return parsed, True
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            day = dt.datetime.strptime(raw, fmt).date()
            return dt.datetime.combine(day, dt.time.min, TZ), False
        except ValueError:
            pass
    if any(ch.isdigit() for ch in raw):
        raise SystemExit(f"Unrecognized Timestamp Issues Raised on CSV row {row_number}: {raw!r}; refusing to send an incomplete report")
    return None, False

def is_customer_footage(row):
    sub_request = (row.get("Sub-request") or "").strip().casefold()
    searchable = " ".join((row.get(k) or "") for k in ("Sub-request", "Issue Details", "Remarks (Incident Details)")).casefold()
    if "ai camera" in searchable or "ai-camera" in searchable:
        return False
    return any(term in searchable for term in ("footage", "video request", "customer request", "requested video")) or sub_request in {"footage", "video", "customer footage"}

issues = []
date_only_or_missing = 0
with SOURCE.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    required = {"Timestamp Issues Raised", "Clients", "Vehicle Number", "Sub-request", "Issue Details", "Remarks (Incident Details)", "Resolved Y/N", "Date - Current Status", "Incident Type"}
    missing = required.difference(reader.fieldnames or [])
    if missing:
        raise SystemExit("Issues- Realtime export is missing expected columns: " + ", ".join(sorted(missing)))
    for row_number, row in enumerate(reader, start=2):
        raised, has_time = parse_timestamp(row.get("Timestamp Issues Raised"), row_number)
        if raised is None:
            continue
        if not has_time:
            if START.date() <= raised.date() <= END.date():
                date_only_or_missing += 1
            continue
        if not (START <= raised < END) or not is_customer_footage(row):
            continue
        incident = (row.get("Incident Type") or "").strip()
        resolved = (row.get("Resolved Y/N") or "").strip() or "Not stated"
        issues.append({
            "client": (row.get("Clients") or "").strip() or "Client not stated",
            "vehicle": (row.get("Vehicle Number") or "").strip() or "Vehicle not stated",
            "priority": "Critical" if incident.casefold() == "critical" else ("No critical" if incident else "Not specified"),
            "request": (row.get("Sub-request") or "").strip() or "Customer footage request",
            "details": (row.get("Issue Details") or "").strip() or "No issue details recorded",
            "remarks": (row.get("Remarks (Incident Details)") or "").strip() or "No remarks recorded",
            "resolved": resolved,
            "status": (row.get("Date - Current Status") or "").strip() or "No current status recorded",
        })

priority_order = {"Critical": 0, "No critical": 1, "Not specified": 2}
issues.sort(key=lambda item: (priority_order[item["priority"]], item["client"].casefold(), item["vehicle"]))
total = len(issues)
critical = sum(item["priority"] == "Critical" for item in issues)
resolved = sum(item["resolved"].casefold() == "yes" for item in issues)
not_resolved = sum(item["resolved"].casefold() == "no" for item in issues)

def pill(label, kind):
    return f'<span class="pill {kind}">{esc(label)}</span>'

cards = []
for item in issues:
    p_class = {"Critical": "critical", "No critical": "normal", "Not specified": "unknown"}[item["priority"]]
    r_class = {"yes": "resolved", "no": "open"}.get(item["resolved"].casefold(), "unknown")
    cards.append(f"""<article class="issue-card">
      <header class="card-head"><div><strong>{esc(item['client'])}</strong><span>Vehicle {esc(item['vehicle'])}</span></div>
        <div class="pills">{pill(item['priority'], p_class)}{pill(item['resolved'], r_class)}</div></header>
      <div class="card-content"><div class="field"><b>Customer footage request</b><strong>{esc(item['request'])}</strong></div>
        <div class="field"><b>Issue details</b><span>{esc(item['details'])}</span></div>
        <div class="field"><b>Remarks</b><span>{esc(item['remarks'])}</span></div>
        <div class="field"><b>Current status</b><span>{esc(item['status'])}</span></div></div>
    </article>""")

no_rows = '<div class="empty">No customer requested footage was raised during this 9 AM–9 AM window.</div>'
date_note = f'<p class="note">{date_only_or_missing} row(s) had no usable timestamp and could not be placed in the 9 AM–9 AM window.</p>' if date_only_or_missing else ""
document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark"><title>Cautio | Customer Footage Report</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;padding:8px;background:#edf2ee;color:#18241d;font:14px/1.35 Arial,Helvetica,sans-serif}}.report{{max-width:600px;margin:0 auto;background:#fff;border:1px solid #d5dfd7;border-radius:10px;overflow:hidden}}
.hero{{padding:12px 15px;background:#12382b;color:#fff}}.logo{{display:block;width:86px;height:26px}}.tagline{{color:#c4d7cb;font-size:10px}}h1{{font-size:18px;line-height:1.15;margin:9px 0 3px}}.subtitle,.window{{color:#d4e0d9;font-size:11px;margin:0}}.window{{margin-top:5px}}
.content{{padding:10px}}.summary{{display:flex;gap:5px;margin:0 0 9px}}.stat{{flex:1;padding:6px 7px;border:1px solid #dce5de;border-radius:6px;background:#f2f7f3}}.stat b{{display:inline;font-size:15px;margin-right:3px}}.stat span{{color:#52635a;font-size:10px}}
.issue-card{{margin-bottom:7px;border:1px solid #d8e1da;border-radius:7px;overflow:hidden;background:#fff}}.issue-card:nth-child(even){{background:#f4f8f5}}.card-head{{display:flex;justify-content:space-between;align-items:center;gap:6px;padding:7px 9px;background:#e9f1eb;border-bottom:1px solid #d8e1da}}.issue-card:nth-child(even) .card-head{{background:#e2ece5}}.card-head strong{{display:block;color:#183e2d;font-size:12px}}.card-head span{{display:block;margin-top:1px;color:#4f6257;font-size:10px}}.pills{{display:flex;gap:4px;align-items:center;flex-wrap:wrap;justify-content:flex-end}}.pill{{display:inline-block;padding:2px 6px;border-radius:10px;background:#e9eeee;color:#26362d;font-size:9px;font-weight:bold;white-space:nowrap}}.pill.critical,.pill.open{{background:#fde8e6;color:#982f27}}.pill.normal,.pill.resolved{{background:#e1f2e8;color:#17643d}}.pill.unknown{{background:#f8f0d8;color:#765514}}
.card-content{{padding:2px 9px 4px}}.field{{display:grid;grid-template-columns:88px minmax(0,1fr);gap:5px;padding:4px 0;border-bottom:1px solid #e8ede9;overflow-wrap:anywhere}}.field:last-child{{border:0}}.field b{{display:block;color:#53665a;font-size:8px;letter-spacing:.25px;text-transform:uppercase}}.field strong,.field span{{font-size:11px;color:#18241d}}.empty{{padding:10px;border:1px solid #d8e1da;border-radius:7px;background:#f4f8f5;color:#45574b}}.note{{margin:0 0 7px;padding:6px;border-left:3px solid #966a13;background:#faf4e3;color:#684e19;font-size:10px}}.footer{{padding:9px 12px;background:#f1f5f2;border-top:1px solid #d8e1da;color:#52635a;font-size:10px}}.footer strong{{display:inline;color:#203b2c;font-size:11px;margin-right:4px}}
@media(max-width:420px){{body{{padding:4px}}.hero{{padding:10px 12px}}.content{{padding:7px}}.field{{grid-template-columns:75px minmax(0,1fr);gap:4px;padding:3px 0}}.field span,.field strong{{font-size:10px}}.stat{{padding:5px}}}}
@media(prefers-color-scheme:dark){{body{{background:#111a15!important;color:#edf5ef!important}}.report,.issue-card{{background:#1c2921!important;border-color:#45564a!important}}.content{{background:#1c2921!important}}.stat,.issue-card:nth-child(even){{background:#24342a!important;border-color:#45564a!important}}.stat span,.card-head span,.field b{{color:#c2d2c7!important}}.stat b,.card-head strong,.field strong{{color:#f1f7f2!important}}.card-head,.issue-card:nth-child(even) .card-head{{background:#2b4032!important;border-color:#45564a!important}}.field{{border-color:#3d4c41!important}}.pill.critical,.pill.open{{background:#542e2c!important;color:#ffb4ad!important}}.pill.normal,.pill.resolved{{background:#244a34!important;color:#a8efbf!important}}.pill.unknown{{background:#4a4028!important;color:#ffe39a!important}}.empty{{background:#24342a!important;color:#e3eee6!important}}.note{{background:#3c3421!important;color:#ffe39a!important}}.footer{{background:#17221b!important;color:#d0ddd4!important;border-color:#45564a!important}}.footer strong{{color:#f1f7f2!important}}}}
</style></head><body><main class="report"><header class="hero"><svg class="logo" viewBox="0 0 120 36" role="img" aria-label="Cautio logo" xmlns="http://www.w3.org/2000/svg"><text x="0" y="28" fill="#FFFFFF" font-family="Arial,Helvetica,sans-serif" font-size="28" font-weight="800" letter-spacing="-1">cautio</text><circle cx="56.3" cy="6.8" r="2.5" fill="#34D399"/></svg>
<div class="tagline">The future of safety on every journey</div><h1>Customer footage report</h1><p class="subtitle">Customer requested footage only · AI camera events excluded</p><p class="window">{START.strftime('%d %b %Y, 9:00 AM')} – {END.strftime('%d %b %Y, 9:00 AM')} IST</p></header>
<section class="content"><div class="summary"><div class="stat"><b>{total}</b><span>Requests</span></div><div class="stat"><b>{critical}</b><span>Critical</span></div><div class="stat"><b>{resolved}</b><span>Resolved</span></div><div class="stat"><b>{not_resolved}</b><span>Not resolved</span></div></div>{''.join(cards) if cards else no_rows}{date_note}</section>
<footer class="footer"><strong>Let's Make Roads Safer, Together</strong>Read-only report from Issues- Realtime</footer></main></body></html>"""
OUTPUT.write_text(document, encoding="utf-8")
print(f"wrote {OUTPUT}; footage_requests={total}; critical={critical}; resolved={resolved}; not_resolved={not_resolved}")

required_mail = ("REPORT_TO", "MAIL_HOST", "MAIL_PORT", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FROM")
missing_mail = [name for name in required_mail if not os.environ.get(name)]
if missing_mail:
    raise SystemExit("Email not configured; missing required GitHub secrets: " + ", ".join(missing_mail))
message = EmailMessage()
message["Subject"] = f"Cautio customer footage report | {START:%d %b} 9 AM–{END:%d %b} 9 AM IST"
message["From"] = os.environ["MAIL_FROM"]
message["To"] = os.environ["REPORT_TO"]
message.set_content(f"{total} customer footage requests, {critical} critical, {resolved} resolved, {not_resolved} not resolved. Open in an HTML-capable mail app for the full report.")
message.add_alternative(document, subtype="html")
with smtplib.SMTP(os.environ["MAIL_HOST"], int(os.environ["MAIL_PORT"]), timeout=30) as server:
    server.starttls()
    server.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
    server.send_message(message)
print("Customer footage report emailed to configured recipient.")
