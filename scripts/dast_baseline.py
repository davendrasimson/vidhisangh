#!/usr/bin/env python3
"""Small, repeatable, non-destructive production DAST baseline.

This checks public exposure, transport, headers, CORS, host validation and
error behaviour. It deliberately does not authenticate, fuzz stored data or
claim to replace an independent penetration test.
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Result:
    name: str
    passed: bool
    evidence: str


def fetch(url: str, *, method: str = "GET", headers=None, data: bytes | None = None):
    request = Request(url, method=method, headers=headers or {}, data=data)
    try:
        response = build_opener(NoRedirect).open(request, timeout=15)
        return response.status, dict(response.headers), response.read(64_000)
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read(64_000)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="vidhisangh.com")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    host = args.host
    base = f"https://{host}"
    results: list[Result] = []

    status, headers, _ = fetch(f"http://{host}/")
    results.append(
        Result(
            "HTTP redirects to HTTPS",
            status in {301, 302, 307, 308}
            and headers.get("Location", "").startswith("https://"),
            f"HTTP {status}, Location={headers.get('Location', '-')[:120]}",
        )
    )

    status, headers, _ = fetch(base + "/")
    lower = {key.lower(): value for key, value in headers.items()}
    required = [
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
    ]
    missing = [name for name in required if name not in lower]
    results.append(
        Result(
            "Browser security headers",
            status == 200 and not missing,
            f"HTTP {status}; missing={','.join(missing) or 'none'}",
        )
    )

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with (
        socket.create_connection((host, 443), timeout=15) as raw,
        context.wrap_socket(raw, server_hostname=host) as tls,
    ):
        negotiated = tls.version() or "unknown"
    results.append(
        Result(
            "Valid certificate and modern TLS",
            negotiated in {"TLSv1.2", "TLSv1.3"},
            f"negotiated={negotiated}; certificate hostname valid",
        )
    )

    for path in (
        "/.env",
        "/.git/config",
        "/server-status",
        "/api/v1/docs",
        "/api/v1/openapi.json",
        "/metrics",
    ):
        code, _, _ = fetch(base + path)
        results.append(
            Result(
                f"Sensitive path blocked: {path}",
                code in {401, 403, 404},
                f"HTTP {code}",
            )
        )

    code, _, _ = fetch(base + "/", method="TRACE")
    results.append(
        Result(
            "TRACE method disabled", code in {400, 403, 404, 405, 501}, f"HTTP {code}"
        )
    )

    code, cors_headers, _ = fetch(
        base + "/health", headers={"Origin": "https://attacker.invalid"}
    )
    allowed_origin = next(
        (
            value
            for key, value in cors_headers.items()
            if key.lower() == "access-control-allow-origin"
        ),
        "",
    )
    results.append(
        Result(
            "Untrusted CORS origin rejected",
            code == 200 and allowed_origin not in {"*", "https://attacker.invalid"},
            f"HTTP {code}; ACAO={allowed_origin or 'absent'}",
        )
    )

    connection = http.client.HTTPSConnection(
        host, 443, context=ssl.create_default_context(), timeout=15
    )
    connection.request("GET", "/health", headers={"Host": "attacker.invalid"})
    response = connection.getresponse()
    response.read()
    connection.close()
    results.append(
        Result(
            "Untrusted Host rejected",
            response.status in {400, 403, 421},
            f"HTTP {response.status}",
        )
    )

    probe = "' OR 1=1--"
    body = json.dumps({"email": probe, "password": "invalid-probe-value"}).encode()
    code, _, response_body = fetch(
        base + "/api/v1/auth/login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=body,
    )
    reflected = probe.encode() in response_body
    results.append(
        Result(
            "Injection-shaped login fails safely",
            code in {401, 422, 429} and not reflected,
            f"HTTP {code}; input_reflected={reflected}",
        )
    )

    passed = sum(result.passed for result in results)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Production DAST baseline",
        "",
        f"**Run:** {now}",
        f"**Target:** `{base}`",
        f"**Result:** {passed}/{len(results)} checks passed",
        "",
        "This is a non-destructive public-surface baseline. It is operating evidence, not an independent penetration-test report.",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for result in results:
        evidence = result.evidence.replace("|", "\\|")
        lines.append(
            f"| {result.name} | {'Pass' if result.passed else 'Fail'} | {evidence} |"
        )
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
