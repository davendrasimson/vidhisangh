#!/usr/bin/env python3
"""Record a failed unit and send a concise SMTP security/operations alert."""

from __future__ import annotations

import os
import re
import smtplib
import ssl
import subprocess
import sys
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

LOG_PATH = Path("/opt/vidhisangh/backups/job-failures.log")
SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@:-]{1,200}$")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _record(unit: str, occurred_at: str) -> None:
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", "40", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        journal = result.stdout[-50_000:]
    except (OSError, subprocess.SubprocessError) as exc:
        journal = f"journal unavailable: {exc.__class__.__name__}\n"
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"=== {occurred_at} {unit} FAILED\n{journal}\n")


def _send(unit: str, occurred_at: str) -> None:
    recipient = _env("VS_SECURITY_ALERT_EMAIL")
    host = _env("VS_SMTP_HOST")
    user = _env("VS_SMTP_USER")
    sender = _env("VS_SMTP_FROM", user)
    password_path = _env("VS_SMTP_PASSWORD_FILE")
    if not all((recipient, host, user, sender, password_path)):
        raise RuntimeError("SMTP alert configuration is incomplete")
    password = Path(password_path).read_text(encoding="utf-8").rstrip("\r\n")
    port = int(_env("VS_SMTP_PORT", "465"))
    use_ssl = _env("VS_SMTP_SSL", "true").lower() in {"1", "true", "yes"}

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[VidhiSangh] service failure: {unit}"
    message.set_content(
        f"VidhiSangh detected a failed service or scheduled job.\n\n"
        f"Unit: {unit}\nTime (UTC): {occurred_at}\n"
        "Review /opt/vidhisangh/backups/job-failures.log and the system journal.\n"
    )
    context = ssl.create_default_context()
    if use_ssl:
        connection = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        connection = smtplib.SMTP(host, port, timeout=15)
    with connection as smtp:
        if not use_ssl and _env("VS_SMTP_TLS", "true").lower() in {"1", "true", "yes"}:
            smtp.starttls(context=context)
        smtp.login(user, password)
        smtp.send_message(message)


def main() -> int:
    unit = sys.argv[1] if len(sys.argv) == 2 else ""
    if not SAFE_UNIT.fullmatch(unit):
        print("Invalid failed-unit name", file=sys.stderr)
        return 2
    occurred_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _record(unit, occurred_at)
    try:
        _send(unit, occurred_at)
        print(f"Failure alert delivered for {unit}")
    except Exception as exc:  # noqa: BLE001  # alerting must never recurse
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"alert delivery failed: {exc.__class__.__name__}\n")
        print(
            f"Failure alert delivery failed: {exc.__class__.__name__}", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
