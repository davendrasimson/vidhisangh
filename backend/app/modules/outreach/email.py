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


def join_url(token: str) -> str:
    """Through the API, which records the click and redirects to sign-up with the invitation token."""
    return f"{_app_url()}/api/v1/outreach/j/{token}"


def register_url(token: str | None) -> str:
    """Where the join link lands: sign-up, carrying the token so the join is attributed."""
    invite = f"invite={token}&" if token else ""
    return f"{_app_url()}/auth/register?{invite}utm_source=invitation&utm_medium=email"


def open_pixel_url(token: str) -> str:
    return f"{_app_url()}/api/v1/outreach/o/{token}.gif"


def court_line(court: str | None, colleagues: int) -> str:
    """'Advocates from the Allahabad High Court are already on VidhiSangh' once a few colleagues have joined."""
    if not court or colleagues < 3:
        return ""
    many = f"{colleagues:,} advocates" if colleagues >= 10 else "Advocates"
    return f"{many} from the {_short_court(court)} have already joined from this list."


def _short_court(court: str) -> str:
    """'Allahabad High Court, Lucknow Bench' → 'Allahabad High Court'; 'District Court, Pune' stays."""
    return court.strip().split(", Lucknow")[0].strip()


def subject_for(court: str | None, colleagues: int = 0) -> str:
    """Short and specific (22 Nov 2026; the old 90-character brand-first subject opened at 13%):
    'Your colleagues at the Allahabad High Court are on VidhiSangh' once a few have joined, else
    'For advocates of the Allahabad High Court: VidhiSangh, free'."""
    if not court or not court.strip():
        return "An invitation to VidhiSangh, India's free legal network"
    c = _short_court(court)
    if colleagues >= 3:
        return f"Your colleagues at the {c} are on VidhiSangh"[:78]
    return f"For advocates of the {c}: VidhiSangh, free"[:78]


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
    join, unsub = join_url(token), unsubscribe_url(token)
    sender = settings.OUTREACH_SENDER_LINE
    subject = subject_for(court, colleagues)
    here = court_line(court, colleagues)
    here_text = f"{here}\n\n" if here else ""
    group_text = f"Your colleagues gather in the {group_name} group: {group_url}\n\n" if group_name and group_url else ""
    points_text = "\n".join(f"• {lead} {rest}" for lead, rest in POINTS)

    first = (name or "").strip().split(" ")
    court_short = _short_court(court) if court and court.strip() else None
    where = f" at the {court_short}" if court_short else ""
    text = f"""{greeting}

VidhiSangh is a free network for India's legal fraternity, and advocates{where} are joining it. I would like you to be among them.

{here_text}Join in one minute (your name and email are already filled in):
{join}

What members use it for:

{points_text}

{ALSO_FREE}

{group_text}VidhiSangh does not advertise or solicit work for advocates; it is a network and knowledge platform.

With regards,
Davendra Singh
VidhiSangh

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
    <img src="{e(_app_url())}/icons/icon-192.png?v=4" width="36" height="36" alt="VidhiSangh" style="vertical-align:middle;border:0;border-radius:8px;">
    <span style="vertical-align:middle;margin-left:8px;font-family:Georgia,'Times New Roman',serif;font-size:22px;font-weight:bold;color:#111827;">Vidhi<span style="color:#d71920;">Sangh</span></span>
  </td></tr>
  <tr><td style="padding:28px 28px 8px;">
    <p style="margin:0 0 14px;font-size:16px;line-height:24px;color:#111827;">{e(greeting)}</p>
    <p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#1f2937;"><strong>VidhiSangh</strong> is a free network for India's legal fraternity, and advocates{e(where)} are joining it. I would like you to be among them.</p>
    {f'<p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#1f2937;"><strong>{e(here)}</strong></p>' if here else ''}
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 10px;"><tr><td style="border-radius:999px;background:#215dcc;">
      <a href="{e(join)}" style="display:inline-block;padding:13px 28px;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:999px;">Join VidhiSangh, free</a>
    </td></tr></table>
    <p style="margin:0 0 18px;font-size:14px;line-height:22px;color:#4b5563;">One minute: your name and email are already filled in; choose a password.</p>
    <p style="margin:0 0 6px;font-size:15px;line-height:24px;color:#1f2937;">What members use it for:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 14px;">{bullets}</table>
    <p style="margin:0 0 18px;font-size:14px;line-height:22px;color:#4b5563;">{e(ALSO_FREE)}</p>
    {f'<p style="margin:0 0 16px;font-size:14px;line-height:22px;color:#4b5563;">Your colleagues gather in the <a href="{e(group_url)}" style="color:#215dcc;">{e(group_name)} group</a>.</p>' if group_name and group_url else ''}
    <p style="margin:0 0 20px;font-size:13px;line-height:20px;color:#6b7280;">VidhiSangh does not advertise or solicit work for advocates; it is a network and knowledge platform.</p>
    <p style="margin:0 0 24px;font-size:15px;line-height:24px;color:#1f2937;">With regards,<br><strong>Davendra Singh</strong><br>VidhiSangh</p>
  </td></tr>
  <tr><td style="padding:18px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;line-height:19px;color:#6b7280;">
    You are receiving this one-time invitation because your professional email address is publicly listed in {e(source)}. We will not email you again unless you join.
    <a href="{e(unsub)}" style="color:#215dcc;">Unsubscribe</a>.<br>
    {e(sender)}. Grievance officer: <a href="mailto:grievance@vidhisangh.com" style="color:#215dcc;">grievance@vidhisangh.com</a>
  </td></tr>
</table>
</td></tr></table>
<img src="{e(open_pixel_url(token))}" width="1" height="1" alt="." style="display:block;border:0;">
</body></html>"""
    return subject, text, body


# ── Follow-ups (22 November 2026) ───────────────────────────────────────
def _shell(*, greeting: str, paragraphs: list[str], join: str, button: str, unsub: str, source: str) -> tuple[str, str]:
    """Plain text and HTML around a short personal message: the paragraphs, one button, the footer."""
    sender = settings.OUTREACH_SENDER_LINE
    text = greeting + "\n\n" + "\n\n".join(paragraphs) + f"\n\n{button}: {join}\n\nWith regards,\nDavendra Singh\nVidhiSangh\n\n—\n" \
        f"You were invited because your professional email address is publicly listed in {source}.\nUnsubscribe: {unsub}\n{sender}. Grievance officer: grievance@vidhisangh.com\n"
    e = html.escape
    paras = "".join(f'<p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#1f2937;">{e(p)}</p>' for p in paragraphs)
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VidhiSangh</title></head>
<body style="margin:0;padding:0;background:#f3f5f9;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f5f9;padding:24px 12px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
  <tr><td style="padding:28px 28px 8px;">
    <p style="margin:0 0 14px;font-size:16px;line-height:24px;color:#111827;">{e(greeting)}</p>
    {paras}
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 18px;"><tr><td style="border-radius:999px;background:#215dcc;">
      <a href="{e(join)}" style="display:inline-block;padding:13px 28px;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:999px;">{e(button)}</a>
    </td></tr></table>
    <p style="margin:0 0 24px;font-size:15px;line-height:24px;color:#1f2937;">With regards,<br><strong>Davendra Singh</strong><br>VidhiSangh</p>
  </td></tr>
  <tr><td style="padding:18px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;line-height:19px;color:#6b7280;">
    You were invited because your professional email address is publicly listed in {e(source)}.
    <a href="{e(unsub)}" style="color:#215dcc;">Unsubscribe</a>.<br>{e(sender)}. Grievance officer: <a href="mailto:grievance@vidhisangh.com" style="color:#215dcc;">grievance@vidhisangh.com</a>
  </td></tr>
</table></td></tr></table>
</body></html>"""
    return text, body


def _greeting(name: str | None) -> str:
    return f"Dear {name.strip()}," if name and name.strip() else "Dear Colleague,"


def build_reminder(*, name: str | None, source: str, token: str, court: str | None = None, colleagues: int = 0,
                   **_: object) -> tuple[str, str, str]:
    """The one reminder, a week after an invitation that was opened but not followed."""
    c = _short_court(court) if court and court.strip() else None
    subject = (f"A reminder: your colleagues at the {c} are on VidhiSangh" if c and colleagues >= 3
               else f"A reminder about VidhiSangh, free for advocates{(' of the ' + c) if c else ''}")[:78]
    here = court_line(court, colleagues)
    paragraphs = [
        "A week ago I invited you to VidhiSangh, the free professional network for India's legal fraternity. In case it went unseen, here it is again.",
        *( [here] if here else [] ),
        "Your name and email are already filled in; joining takes a minute and costs nothing. If it is not for you, ignore this and you will not hear from me again.",
    ]
    text, body = _shell(greeting=_greeting(name), paragraphs=paragraphs, join=join_url(token), button="Join VidhiSangh, free",
                        unsub=unsubscribe_url(token), source=source)
    return subject, text, body


def build_personal(*, name: str | None, source: str, token: str, note: str, joined: bool) -> tuple[str, str, str]:
    """A note the admin typed, in the same shell. Joined members get a sign-in button, invitees the join link."""
    subject = "A note from Davendra Singh, VidhiSangh"
    paragraphs = [p.strip() for p in note.replace("\r", "").split("\n\n") if p.strip()]
    join = f"{_app_url()}/auth/login" if joined else join_url(token)
    text, body = _shell(greeting=_greeting(name), paragraphs=paragraphs, join=join,
                        button="Open VidhiSangh" if joined else "Join VidhiSangh, free",
                        unsub=unsubscribe_url(token), source=source)
    return subject, text, body


def draft_note(*, name: str | None, court: str | None, joined: bool, colleagues: int = 0) -> str:
    """A starting point for the admin's personal note; edited before sending."""
    first = (name or "").replace("Adv.", "").strip().split(" ")[0] or "Colleague"
    c = _short_court(court) if court and court.strip() else "your court"
    if joined:
        return (f"{first}, thank you for joining VidhiSangh. I am building it for advocates like you, and I would value "
                f"two minutes of your view: what should it do for the {c} bar that nothing else does?\n\n"
                f"Reply to this email or message me on WhatsApp. And do add the courts you practise in on your profile, "
                f"so colleagues from the {c} can find you.")
    many = f"{colleagues} advocates from the {c} have already joined. " if colleagues >= 3 else ""
    return (f"{first}, you opened the VidhiSangh invitation and reached the sign-up page, so I wanted to write personally. "
            f"{many}It is free, it is built for the Indian bar, and it takes a minute to join; your details are already filled in.\n\n"
            f"If something stopped you, reply and tell me, I read every answer.")
