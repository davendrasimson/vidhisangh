"""Register (or list) the Brevo transactional webhook that feeds invitation engagement.

Needs a Brevo **v3 API key** (`xkeysib-…`, Brevo → SMTP & API → API keys), not the SMTP
key the relay uses: ``BREVO_API_KEY`` in the environment or ``BREVO_API_KEY_FILE``.
The webhook URL is ``<PUBLIC_APP_URL>/api/v1/outreach/events/<VS_OUTREACH_WEBHOOK_SECRET>``.

    python -m app.scripts.brevo_webhook            # show the account's webhooks
    python -m app.scripts.brevo_webhook --create   # add ours if it is not there yet

Prints ids and URLs with the secret masked; never prints the key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from app.core.config import settings

API = "https://api.brevo.com/v3"
EVENTS = ["delivered", "hardBounce", "softBounce", "blocked", "spam", "invalid", "deferred", "opened", "click", "unsubscribed"]


def _key() -> str:
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key and os.environ.get("BREVO_API_KEY_FILE"):
        key = Path(os.environ["BREVO_API_KEY_FILE"]).read_text(encoding="utf-8").strip()
    if not key.startswith("xkeysib-"):
        sys.exit("Set BREVO_API_KEY (or BREVO_API_KEY_FILE) to a Brevo v3 API key (xkeysib-…).")
    return key


def _call(method: str, path: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}/{path}", data=data, method=method,
                                 headers={"api-key": _key(), "accept": "application/json", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        sys.exit(f"Brevo answered HTTP {exc.code}: {exc.read().decode()[:300]}")


def _mask(url: str, secret: str) -> str:
    return url.replace(secret, "<secret>") if secret else url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--create", action="store_true", help="create the webhook if it does not exist")
    args = parser.parse_args()

    secret = settings.OUTREACH_WEBHOOK_SECRET or ""
    if args.create and not secret:
        sys.exit("VS_OUTREACH_WEBHOOK_SECRET is not set; set it in the API unit first (the route answers 404 without it).")
    ours = f"{settings.PUBLIC_APP_URL.rstrip('/')}/api/v1/outreach/events/{secret}"

    existing = _call("GET", "webhooks?type=transactional")
    hooks = existing.get("webhooks", []) if isinstance(existing, dict) else []
    for hook in hooks:
        print(f"  #{hook.get('id')}  {_mask(hook.get('url', ''), secret)}  events={','.join(hook.get('events', []))}")
    present = any(h.get("url") == ours for h in hooks)
    if not args.create:
        print("ours is registered" if present else "ours is NOT registered (run with --create)")
        return
    if present:
        print("Already registered; nothing to do.")
        return
    created = _call("POST", "webhooks", {
        "url": ours, "type": "transactional", "events": EVENTS,
        "description": "VidhiSangh invitation engagement (delivered, bounces, opens, clicks, complaints)",
    })
    print("Created webhook", created.get("id") if isinstance(created, dict) else created, "→", _mask(ours, secret))


if __name__ == "__main__":
    main()
