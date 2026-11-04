"""Submit or check a WhatsApp message template (Meta Business Management API).

    python -m app.scripts.whatsapp_template --status vidhisangh_daily      # status per language
    python -m app.scripts.whatsapp_template --submit vidhisangh_daily      # create en + hi (idempotent: skips languages that exist)
    python -m app.scripts.whatsapp_template --show vidhisangh_daily        # print the definition, no API call

Needs the number's access token: VS_WA_ACCESS_TOKEN_FILE, or the ``wa_access_token``
credential of the unit it runs in ($CREDENTIALS_DIRECTORY). Never prints the token.
Only the templates defined in TEMPLATES below can be submitted; earlier templates
(product_update, judicial_officer_update, fraternity_invite, sc_daily_orders) were
submitted by hand and are listed in DEPLOYMENT.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

from app.core.config import settings

APP = settings.PUBLIC_APP_URL.rstrip("/")

# VidhiSangh Daily: the morning brief's lead, Monday to Saturday, to members who said yes
# (consent topic ``daily``). Three body parameters: first name, the lead's title, one line.
# The button opens the page; replies to the number are not received, so the footer points
# to Settings instead of "reply STOP".
TEMPLATES: dict[str, dict[str, list[dict]]] = {
    "vidhisangh_daily": {
        "en": [
            {"type": "HEADER", "format": "TEXT", "text": "VidhiSangh Daily"},
            {"type": "BODY",
             "text": ("Hi {{1}}, today's brief is ready.\n\n*{{2}}*\n{{3}}\n\n"
                      "The question, the section of the day, the Supreme Court judgment and who joined near you are in the app."),
             "example": {"body_text": [["Asha", "Today's question",
                                        "Under the Bharatiya Nyaya Sanhita, which section now carries the punishment for murder?"]]}},
            {"type": "FOOTER", "text": "Monday to Saturday. Switch off in Settings → Notifications."},
            {"type": "BUTTONS", "buttons": [
                {"type": "URL", "text": "Open today's brief", "url": f"{APP}/app/daily?from=whatsapp"},
            ]},
        ],
        "hi": [
            {"type": "HEADER", "format": "TEXT", "text": "VidhiSangh Daily"},
            {"type": "BODY",
             "text": ("नमस्ते {{1}} जी, आज का ब्रीफ़ तैयार है।\n\n*{{2}}*\n{{3}}\n\n"
                      "आज का प्रश्न, आज की धारा, सर्वोच्च न्यायालय का निर्णय और आपके शहर में कौन जुड़ा, सब ऐप में।"),
             "example": {"body_text": [["Asha", "Today's question",
                                        "Under the Bharatiya Nyaya Sanhita, which section now carries the punishment for murder?"]]}},
            {"type": "FOOTER", "text": "सोमवार से शनिवार। बंद करने के लिए Settings → Notifications।"},
            {"type": "BUTTONS", "buttons": [
                {"type": "URL", "text": "आज का ब्रीफ़ खोलें", "url": f"{APP}/app/daily?from=whatsapp"},
            ]},
        ],
    },
}


def _token() -> str:
    path = settings.WA_ACCESS_TOKEN_FILE or (
        os.path.join(os.environ["CREDENTIALS_DIRECTORY"], "wa_access_token") if os.environ.get("CREDENTIALS_DIRECTORY") else "")
    if settings.WA_ACCESS_TOKEN:
        return settings.WA_ACCESS_TOKEN
    if path:
        return Path(path).read_text().strip()
    sys.exit("no WhatsApp token: set VS_WA_ACCESS_TOKEN_FILE or run inside a unit with the wa_access_token credential")


def _base() -> str:
    return f"https://graph.facebook.com/{settings.WA_API_VERSION}/{settings.WA_BUSINESS_ACCOUNT_ID}/message_templates"


def status(client: httpx.Client, name: str) -> list[dict]:
    r = client.get(_base(), params={"name": name, "fields": "name,language,status,category,rejected_reason,id"})
    r.raise_for_status()
    return [t for t in r.json().get("data", []) if t.get("name") == name]


def submit(client: httpx.Client, name: str) -> list[dict]:
    existing = {t["language"] for t in status(client, name)}
    out = []
    for lang, components in TEMPLATES[name].items():
        if lang in existing:
            out.append({"language": lang, "result": "exists"})
            continue
        r = client.post(_base(), json={"name": name, "language": lang, "category": "MARKETING",
                                       "allow_category_change": True, "components": components})
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            err = body.get("error", {})
            out.append({"language": lang, "result": "error", "code": err.get("code"),
                        "message": err.get("error_user_msg") or err.get("message")})
        else:
            out.append({"language": lang, "result": body.get("status", "submitted"), "id": body.get("id")})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", metavar="NAME")
    group.add_argument("--submit", metavar="NAME", choices=sorted(TEMPLATES))
    group.add_argument("--show", metavar="NAME", choices=sorted(TEMPLATES))
    args = parser.parse_args()
    if args.show:
        print(json.dumps(TEMPLATES[args.show], ensure_ascii=False, indent=2))
        return
    with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {_token()}"}) as client:
        result = submit(client, args.submit) if args.submit else status(client, args.status)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
