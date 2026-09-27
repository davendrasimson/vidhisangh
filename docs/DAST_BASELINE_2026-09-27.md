# Production DAST baseline

**Run:** 2026-09-27T17:04:44Z
**Target:** `https://vidhisangh.com`
**Result:** 13/13 checks passed

This is a non-destructive public-surface baseline. It is operating evidence, not an independent penetration-test report.

| Check | Result | Evidence |
|---|---|---|
| HTTP redirects to HTTPS | Pass | HTTP 301, Location=https://vidhisangh.com/ |
| Browser security headers | Pass | HTTP 200; missing=none |
| Valid certificate and modern TLS | Pass | negotiated=TLSv1.3; certificate hostname valid |
| Sensitive path blocked: /.env | Pass | HTTP 404 |
| Sensitive path blocked: /.git/config | Pass | HTTP 404 |
| Sensitive path blocked: /server-status | Pass | HTTP 404 |
| Sensitive path blocked: /api/v1/docs | Pass | HTTP 404 |
| Sensitive path blocked: /api/v1/openapi.json | Pass | HTTP 404 |
| Sensitive path blocked: /metrics | Pass | HTTP 404 |
| TRACE method disabled | Pass | HTTP 405 |
| Untrusted CORS origin rejected | Pass | HTTP 200; ACAO=absent |
| Untrusted Host rejected | Pass | HTTP 400 |
| Injection-shaped login fails safely | Pass | HTTP 422; input_reflected=False |
