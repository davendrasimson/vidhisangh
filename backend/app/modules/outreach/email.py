"""The invitation email: plain text + HTML, with one-click unsubscribe.

Written for advocates and other legal professionals who have never heard of
VidhiSangh: who we are, what is free, one clear button, why they received it
(the public listing it came from), and how to never hear from us again. One
invitation per address; there are no follow-ups.
"""

from __future__ import annotations

import html

from app.core.config import settings

SUBJECT = "An invitation to VidhiSangh, the free professional network for India's legal fraternity"


def _app_url() -> str:
    return settings.PUBLIC_APP_URL.rstrip("/")


def unsubscribe_url(token: str) -> str:
    """The page people land on from the email's link."""
    return f"{_app_url()}/unsubscribe/{token}"


def one_click_url(token: str) -> str:
    """RFC 8058 target: mail apps POST here when the reader taps their own Unsubscribe."""
    return f"{_app_url()}/api/v1/outreach/unsubscribe/{token}"


def join_url() -> str:
    return f"{_app_url()}/auth/register?utm_source=invitation&utm_medium=email"


def build(*, name: str | None, source: str, token: str) -> tuple[str, str, str]:
    """(subject, text, html) for one contact."""
    greeting = f"Dear {name.strip()}," if name and name.strip() else "Dear Colleague,"
    join, unsub = join_url(), unsubscribe_url(token)
    address = settings.OUTREACH_POSTAL_ADDRESS

    text = f"""{greeting}

I am writing to invite you to VidhiSangh (vidhisangh.com), a professional network built for India's legal fraternity: advocates, judges, legal researchers, law students, munshis, law firms and corporate legal teams.

It is free to join, and members use it to:

• Connect with colleagues across courts and cities, and follow practice updates in one feed
• Read BNS, BNSS and BSA section by section, each linked to the corresponding IPC, CrPC or Evidence Act provision
• Search Supreme Court and High Court judgments by party, advocate, judge, Act or section
• Keep matters, hearings, documents and invoices in one place, if you want practice tools as well

Signing up takes about a minute, with your WhatsApp number or email:
{join}

VidhiSangh is a network and knowledge platform. It does not advertise or solicit work for advocates.

With regards,
Team VidhiSangh

—
You are receiving this one-time invitation because your professional email address is publicly listed in {source}. We will not email you again unless you join.
Unsubscribe: {unsub}
VidhiSangh is developed and managed by {address}. Grievance officer: grievance@vidhisangh.com
"""

    e = html.escape
    bullets = "".join(
        f'<tr><td style="padding:6px 10px 6px 0;vertical-align:top;color:#215dcc;font-size:18px;line-height:22px;">&#10003;</td>'
        f'<td style="padding:6px 0;font-size:15px;line-height:22px;color:#1f2937;">{item}</td></tr>'
        for item in (
            "<strong>Connect with colleagues</strong> across courts and cities, and follow practice updates in one feed",
            "<strong>Read BNS, BNSS and BSA</strong> section by section, each linked to the corresponding IPC, CrPC or Evidence Act provision",
            "<strong>Search Supreme Court and High Court judgments</strong> by party, advocate, judge, Act or section",
            "<strong>Keep matters, hearings, documents and invoices</strong> in one place, if you want practice tools as well",
        )
    )
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(SUBJECT)}</title></head>
<body style="margin:0;padding:0;background:#f3f5f9;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f5f9;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
  <tr><td style="padding:22px 28px;border-bottom:1px solid #e5e7eb;">
    <img src="{e(_app_url())}/icons/icon-192.png?v=4" width="36" height="36" alt="" style="vertical-align:middle;border:0;border-radius:8px;">
    <span style="vertical-align:middle;margin-left:8px;font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:bold;color:#111827;">Vidhi<span style="color:#d71920;">Sangh</span></span>
  </td></tr>
  <tr><td style="padding:28px 28px 8px;">
    <p style="margin:0 0 14px;font-size:16px;line-height:24px;color:#111827;">{e(greeting)}</p>
    <p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#1f2937;">I am writing to invite you to <strong>VidhiSangh</strong>, a professional network built for India's legal fraternity: advocates, judges, legal researchers, law students, munshis, law firms and corporate legal teams.</p>
    <p style="margin:0 0 6px;font-size:15px;line-height:24px;color:#1f2937;">It is <strong>free to join</strong>, and members use it to:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 18px;">{bullets}</table>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px;"><tr><td style="border-radius:999px;background:#215dcc;">
      <a href="{e(join)}" style="display:inline-block;padding:13px 28px;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:999px;">Join VidhiSangh free</a>
    </td></tr></table>
    <p style="margin:0 0 16px;font-size:14px;line-height:22px;color:#4b5563;">Signing up takes about a minute, with your WhatsApp number or email.</p>
    <p style="margin:0 0 20px;font-size:13px;line-height:20px;color:#6b7280;">VidhiSangh is a network and knowledge platform. It does not advertise or solicit work for advocates.</p>
    <p style="margin:0 0 24px;font-size:15px;line-height:24px;color:#1f2937;">With regards,<br><strong>Team VidhiSangh</strong></p>
  </td></tr>
  <tr><td style="padding:18px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;line-height:19px;color:#6b7280;">
    You are receiving this one-time invitation because your professional email address is publicly listed in {e(source)}. We will not email you again unless you join.
    <a href="{e(unsub)}" style="color:#215dcc;">Unsubscribe</a>.<br>
    VidhiSangh is developed and managed by {e(address)}. Grievance officer: <a href="mailto:grievance@vidhisangh.com" style="color:#215dcc;">grievance@vidhisangh.com</a>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    return SUBJECT, text, body
