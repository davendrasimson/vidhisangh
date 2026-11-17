"""VidhiSangh Daily as an email: the same brief, lead first, for members without the app.

Plain text and HTML (inline styles; mail apps strip stylesheets). Every item
links to the public page where one exists (bare-act section, judgment headnote,
news source) and to the app otherwise, so the email is useful without signing
in. The quiz shows the question only; the answer waits in the app.
"""

from __future__ import annotations

from datetime import date
from html import escape

from app.core.channels import ChannelMessage
from app.core.config import settings
from app.modules.identity.models import User
from app.modules.notifications.whatsapp_updates import first_name

SITE = "https://vidhisangh.com"
TITLES = {"section": "Section of the day", "judgment": "Judgment of the day", "quiz": "Today's question",
          "on_this_day": "On this day", "news": "The week in law", "fraternity": "Your fraternity"}
ORDER = ["quiz", "section", "judgment", "on_this_day", "news"]


def base_url() -> str:
    return settings.PUBLIC_APP_URL.rstrip("/") or SITE


def _item(kind: str, brief: dict) -> tuple[str, str, str | None, str | None] | None:
    """(heading, title, line, url) for one card, or None when the day has no such card."""
    if kind == "quiz" and brief.get("quiz"):
        q = brief["quiz"]
        opts = "  ".join(f"({'ABCD'[i]}) {o}" for i, o in enumerate(q["options"]))
        return TITLES["quiz"] + f" · {q['topic']}", q["question"], opts, f"{base_url()}/app/daily?from=email"
    if kind == "section" and brief.get("section"):
        s = brief["section"]
        return TITLES["section"], s["title"], s.get("description"), s.get("url")
    if kind == "judgment" and brief.get("judgment"):
        j = brief["judgment"]
        return "Supreme Court · " + TITLES["judgment"], j["title"], j.get("description"), j.get("url")
    if kind == "on_this_day" and brief.get("on_this_day"):
        o = brief["on_this_day"]
        url = f"{SITE}/judgments/{o['judgment_id']}/" if o.get("judgment_id") else None
        when = f"Decided {o['decided'].strftime('%d/%m/%Y')}" + (f" · {o['citation']}" if o.get("citation") else "")
        return f"{TITLES['on_this_day']} in {o['decided'].year}", o["case"], f"{when}. {o['holding']}", url
    if kind == "news" and brief.get("news"):
        lines = "; ".join(n["title"] for n in brief["news"][:3])
        return TITLES["news"], lines, None, brief["news"][0].get("url")
    return None


def _court_block(court: dict | None) -> tuple[str, str]:
    """Text and HTML for the member's court card, when its lists are known."""
    if not court or not (court.get("today") or court.get("next")):
        return "", ""
    day = court.get("today") or court["next"]
    when = "today" if court.get("today") else day["for_date"].strftime("%A %d/%m/%Y")
    labels = ", ".join(l["label"] for l in day["lists"][:6])
    page = f"{SITE}/courts/{court['slug']}/cause-list/"
    text = f"\nYOUR COURT · {court['name']}\nCause lists for {when}: {labels}.\n{page}\n"
    html = (f'<tr><td style="padding:14px 20px;border-top:1px solid #e6e8ef">'
            f'<div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#1f4e8c;font-weight:700">Your court · {escape(court["name"])}</div>'
            f'<div style="margin-top:4px;font-size:15px;color:#1a1d29">Cause lists for {escape(when)}: {escape(labels)}.</div>'
            f'<div style="margin-top:6px"><a href="{escape(page)}" style="color:#1f4e8c">Open the lists</a></div></td></tr>')
    return text, html


def render(user: User, brief: dict, court: dict | None, day: date, unsubscribe_url: str) -> ChannelMessage:
    lead = brief["lead"]
    kinds = [lead] + [k for k in ORDER if k != lead]
    items = [(k, _item(k, brief)) for k in kinds]
    items = [(k, it) for k, it in items if it]
    name = first_name(user.full_name, "en")
    day_text = day.strftime("%A %d/%m/%Y")
    open_url = f"{base_url()}/app/daily?from=email"
    settings_url = f"{base_url()}/app/settings/notifications"
    lead_item = items[0][1] if items else None
    subject = f"{TITLES[lead]}: {lead_item[1]}"[:120] if lead_item else f"VidhiSangh Daily, {day_text}"
    court_text, court_html = _court_block(court)

    text = [f"VidhiSangh Daily · {day_text}", f"Good morning, {name}." if name else "Good morning.", ""]
    html = [f'<tr><td style="padding:18px 20px 6px"><div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#5d6477">VidhiSangh Daily · {escape(day_text)}</div>'
            f'<div style="margin-top:6px;font-size:16px;color:#1a1d29">Good morning{", " + escape(name) if name else ""}.</div></td></tr>']
    for k, (heading, title, line, url) in items:
        text += [heading.upper(), title] + ([line] if line else []) + ([url] if url else []) + [""]
        link = f'<div style="margin-top:6px"><a href="{escape(url)}" style="color:#1f4e8c">{"Answer in the app" if k == "quiz" else "Read more"}</a></div>' if url else ""
        html.append(
            f'<tr><td style="padding:14px 20px;border-top:1px solid #e6e8ef">'
            f'<div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#1f4e8c;font-weight:700">{escape(heading)}</div>'
            f'<div style="margin-top:4px;font-size:{"18" if k == lead else "15"}px;font-weight:600;color:#1a1d29">{escape(title)}</div>'
            + (f'<div style="margin-top:4px;font-size:14px;color:#3a3f52;line-height:1.5">{escape(line)}</div>' if line else "")
            + link + "</td></tr>")
    text.append(court_text)
    html.append(court_html)
    text += [f"Open today's brief: {open_url}", "",
             "You get VidhiSangh Daily by email because you are a member without the app.",
             f"Stop these emails: {unsubscribe_url}", f"Settings: {settings_url}"]
    html.append(
        f'<tr><td style="padding:18px 20px;border-top:1px solid #e6e8ef"><a href="{escape(open_url)}" '
        f'style="display:inline-block;background:#1f4e8c;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:600">Open today\'s brief</a></td></tr>'
        f'<tr><td style="padding:12px 20px 20px;font-size:12px;color:#5d6477;line-height:1.5">You get VidhiSangh Daily by email because you are a member without the app. '
        f'<a href="{escape(unsubscribe_url)}" style="color:#5d6477">Stop these emails</a> · <a href="{escape(settings_url)}" style="color:#5d6477">Settings</a></td></tr>')
    html_doc = ('<!doctype html><html lang="en"><body style="margin:0;background:#f6f7fb;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7fb;padding:20px 0"><tr><td align="center">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border:1px solid #e6e8ef;border-radius:14px">'
                + "".join(html) + "</table></td></tr></table></body></html>")
    return ChannelMessage(to_email=user.email, to_name=user.full_name, subject=subject, body="\n".join(text),
                          html=html_doc, unsubscribe_url=unsubscribe_url)
