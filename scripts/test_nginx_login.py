"""Exercise the edge login routing on isolated loopback ports.

Run on a host with nginx, the installed snippets/certificates and API on :8000:
    sudo python3 test_nginx_login.py /path/to/candidate/vidhisangh.conf
Production listeners/configuration are not modified. No credentials are sent.
"""
import http.client
import json
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import tempfile
import time


def main():
    candidate = Path(sys.argv[1]).read_text()
    # Use the real server blocks, includes and upstream, isolated from live ports.
    candidate = re.sub(r"listen\s+(?:\[::\]:)?80;", "listen 127.0.0.1:18080;", candidate)
    candidate = re.sub(r"listen\s+(?:\[::\]:)?443 ssl http2", "listen 127.0.0.1:18443 ssl http2", candidate)
    # IPv4/IPv6 listeners now coincide: retain one of each per server block.
    candidate = re.sub(r"(    listen [^\n]+\n)\1", r"\1", candidate)
    candidate = candidate.replace("include             snippets/", "include /etc/nginx/snippets/")
    candidate = candidate.replace("include snippets/", "include /etc/nginx/snippets/")
    with tempfile.TemporaryDirectory(prefix="vs-nginx-login-") as directory:
        root = Path(directory)
        candidate = re.sub(r"/var/log/nginx/[\w.-]+", str(root / "requests.log"), candidate)
        config = root / "nginx.conf"
        pid = root / "nginx.pid"
        config.write_text(
            f"pid {pid};\nerror_log {root}/error.log;\nevents {{}}\nhttp {{\n{candidate}\n}}\n"
        )
        command = ["/usr/sbin/nginx", "-p", "/etc/nginx/", "-c", str(config)]
        subprocess.run([*command, "-t"], check=True)
        subprocess.run(command, check=True)
        try:
            time.sleep(0.2)

            def request(host, method, path, body=None, tls=True):
                connection = (
                    http.client.HTTPSConnection("127.0.0.1", 18443, context=ssl._create_unverified_context(), timeout=10)
                    if tls else http.client.HTTPConnection("127.0.0.1", 18080, timeout=10)
                )
                try:
                    connection.request(method, path, body, {"Host": host, "Content-Type": "application/json"})
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
                finally:
                    connection.close()

            for host in ("www.vidhisangh.com", "vidhisangh.com"):
                status, headers, body = request(host, "POST", "/api/v1/auth/login", "{}")
                assert status == 422, (host, status, body)
                assert "Location" not in headers
                assert json.loads(body)["status"] == 422
                print(f"PASS {host}: login POST reaches API validation without redirect")

            status, _, _ = request("www.vidhisangh.com", "GET", "/api/v1/auth/me")
            assert status == 401, status
            print("PASS www current-user request reaches API authentication")

            path = "/auth/login?returnUrl=%2Fapp%2Fdashboard"
            status, headers, _ = request("www.vidhisangh.com", "GET", path)
            assert status == 308 and headers["Location"] == f"https://vidhisangh.com{path}"
            print("PASS page redirect preserves path and query")

            status, headers, _ = request("www.vidhisangh.com", "POST", "/api/v1/auth/login", "{}", tls=False)
            assert status == 308 and headers["Location"] == "https://www.vidhisangh.com/api/v1/auth/login"
            print("PASS HTTP upgrade uses method-preserving redirect")
        finally:
            # Stop only this isolated instance, never the systemd service.
            if pid.exists():
                import os
                os.kill(int(pid.read_text()), signal.SIGQUIT)
                time.sleep(0.2)


if __name__ == "__main__":
    main()
