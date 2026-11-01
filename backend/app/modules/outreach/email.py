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


def court_line(court: str | None, colleagues: int) -> str:
    """'Advocates from the Allahabad High Court are already on VidhiSangh' once a few colleagues have joined."""
    if not court or colleagues < 5:
        return ""
    many = f"{colleagues:,} advocates" if colleagues >= 20 else "Advocates"
    return f"{many} from the {court.strip()} are already on VidhiSangh."


def subject_for(court: str | None) -> str:
    """Court-aware subject: 'Advocates of the Allahabad High Court: an invitation to VidhiSangh'."""
    return f"Advocates of the {court.strip()}: an invitation to VidhiSangh, the fraternity's free network" if court and court.strip() else SUBJECT


# What members do on VidhiSangh, network first; practice tools and research are the free extras.
POINTS: tuple[tuple[str, str], ...] = (
    ("Find your colleagues", "from your court, your city and your bar, and connect with seniors, peers and juniors across India"),
    ("Join your court's group", "and communities by practice area: ask a senior, help a junior, share a notice or a judgment"),
    ("Follow the fraternity's feed", "of what advocates are discussing today, and message colleagues directly"),
    ("Find local counsel", "in another city or before another bench, with no referral fee"),
)
ALSO_FREE = "Also free, for when you want them: 5.9 million Supreme Court and High Court judgments, Bare Acts including BNS, BNSS and BSA, and tools to keep your matters and dates."


def build(*, name: str | None, source: str, token: str, court: str | None = None, colleagues: int = 0,
          group_name: str | None = None, group_url: str | None = None) -> tuple[str, str, str]:
    """(subject, text, html) for one contact. `court` and `colleagues` add the "already here" line; `group_*`
    name the court's community group to join."""
    greeting = f"Dear {name.strip()}," if name and name.strip() else "Dear Colleague,"
    join, unsub = join_url(), unsubscribe_url(token)
    sender = settings.OUTREACH_SENDER_LINE
    subject = subject_for(court)
    here = court_line(court, colleagues)
    here_text = f"{here}\n\n" if here else ""
    group_text = f"Your colleagues gather in the {group_name} group: {group_url}\n\n" if group_name and group_url else ""
    points_text = "\n".join(f"• {lead} {rest}" for lead, rest in POINTS)

    text = f"""{greeting}

I am writing to invite you to VidhiSangh (vidhisangh.com), the free professional network for India's legal fraternity: a place to find and stay in touch with the advocates you work alongside, and the ones you should know.

{here_text}It is free to join, and members use it to:

{points_text}

{ALSO_FREE}

Signing up takes about a minute, with your WhatsApp number or email:
{join}

{group_text}VidhiSangh is a network and knowledge platform. It does not advertise or solicit work for advocates.

With regards,
Team VidhiSangh

—
You are receiving this one-time invitation because your professional email address is publicly listed in {source}. We will not email you again unless you join.
Unsubscribe: {unsub}
{sender}. Grievance officer: grievance@vidhisangh.com
"""

    e = html.escape
    bullets = "".join(
        f'<tr><td style="padding:6px 10px 6px 0;vertical-align:top;color:#215dcc;font-size:18px;line-height:22px;">&#10003;</td>'
        f'<td style="padding:6px 0;font-size:15px;line-height:22px;color:#1f2937;"><strong>{e(lead)}</strong> {e(rest)}</td></tr>'
        for lead, rest in POINTS
    )
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(subject)}</title></head>
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
    <p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#1f2937;">I am writing to invite you to <strong>VidhiSangh</strong>, the free professional network for India's legal fraternity: a place to find and stay in touch with the advocates you work alongside, and the ones you should know.</p>
    {f'<p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#1f2937;"><strong>{e(here)}</strong></p>' if here else ''}
    <p style="margin:0 0 6px;font-size:15px;line-height:24px;color:#1f2937;">It is <strong>free to join</strong>, and members use it to:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 14px;">{bullets}</table>
    <p style="margin:0 0 18px;font-size:14px;line-height:22px;color:#4b5563;">{e(ALSO_FREE)}</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px;"><tr><td style="border-radius:999px;background:#215dcc;">
      <a href="{e(join)}" style="display:inline-block;padding:13px 28px;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:999px;">Join VidhiSangh free</a>
    </td></tr></table>
    <p style="margin:0 0 16px;font-size:14px;line-height:22px;color:#4b5563;">Signing up takes about a minute, with your WhatsApp number or email.</p>
    {f'<p style="margin:0 0 16px;font-size:14px;line-height:22px;color:#4b5563;">Your colleagues gather in the <a href="{e(group_url)}" style="color:#215dcc;">{e(group_name)} group</a>.</p>' if group_name and group_url else ''}
    <p style="margin:0 0 20px;font-size:13px;line-height:20px;color:#6b7280;">VidhiSangh is a network and knowledge platform. It does not advertise or solicit work for advocates.</p>
    <p style="margin:0 0 24px;font-size:15px;line-height:24px;color:#1f2937;">With regards,<br><strong>Team VidhiSangh</strong></p>
  </td></tr>
  <tr><td style="padding:18px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;line-height:19px;color:#6b7280;">
    You are receiving this one-time invitation because your professional email address is publicly listed in {e(source)}. We will not email you again unless you join.
    <a href="{e(unsub)}" style="color:#215dcc;">Unsubscribe</a>.<br>
    {e(sender)}. Grievance officer: <a href="mailto:grievance@vidhisangh.com" style="color:#215dcc;">grievance@vidhisangh.com</a>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    return subject, text, body
