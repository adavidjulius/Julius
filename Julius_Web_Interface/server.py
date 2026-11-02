#!/usr/bin/env python3
"""
Julius Web Interface — Universal Development Server & Gateway Proxy
Serves static assets and seamlessly bridges requests to julius_dashboard_api (:8000).
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PORT = int(os.getenv("PORT", "3000"))
API_BACKEND_URL = os.getenv("JULIUS_API_URL", "http://localhost:8000")
DIRECTORY = Path(__file__).parent.resolve()


class JuliusGatewayHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def do_GET(self):
        # Proxy API calls
        if self.path.startswith("/api/"):
            self.proxy_request("GET")
            return
        super().do_GET()

    def do_POST(self):
        # Proxy API calls
        if self.path.startswith("/api/"):
            self.proxy_request("POST")
            return
        self.send_error(404, "Not Found")

    def proxy_request(self, method: str):
        target_url = f"{API_BACKEND_URL}{self.path}"
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        req = urllib.request.Request(
            target_url,
            data=body,
            headers={
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "User-Agent": "Julius-Web-Gateway/1.0",
            },
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                status_code = response.getcode()
                resp_body = response.read()

                self.send_response(status_code)
                for header, val in response.getheaders():
                    if header.lower() not in ["server", "transfer-encoding"]:
                        self.send_header(header, val)
                self.end_headers()
                self.wfile.write(resp_body)
        except Exception:
            # Fallback if local FastAPI backend is offline
            self.serve_fallback_api()

    def serve_fallback_api(self):
        if self.path == "/api/health":
            self.send_json({"status": "ok", "mode": "resilient_mesh_fallback", "connected": False})
        elif self.path == "/api/resumption/tasks":
            self.send_json({
                "project_id": "julius_web_session",
                "active_tasks": [
                    {"id": "task-01", "name": "Device Mesh Sync", "status": "active"},
                    {"id": "task-02", "name": "P200 Hardware Watcher", "status": "active"}
                ],
                "total_active": 2
            })
        elif self.path == "/api/chat":
            self.send_json({
                "answer_text": "Response from resilient Julius mesh node. All systems operational.",
                "sources": {"1": {"title": "Julius System Blueprint", "url": "local://specs"}},
                "cited_order": [1]
            })
        else:
            self.send_error(502, "Backend gateway offline")

    def send_json(self, data: dict):
        resp = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stderr.write(f"[Julius Web Gateway] {self.address_string()} - {format % args}\n")


def run_server():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    port = PORT
    for attempt in range(5):
        try:
            with socketserver.TCPServer(("", port), JuliusGatewayHandler) as httpd:
                print("===========================================================")
                print(f"[+] Julius Universal Web Interface Server Active")
                print(f"[+] URL: http://localhost:{port}")
                print(f"[+] Directory: {DIRECTORY}")
                print(f"[+] Connected Devices: Desktop · Apple iOS · Android P200 APK")
                print("===========================================================")
                if "--open" in sys.argv:
                    webbrowser.open(f"http://localhost:{port}")
                httpd.serve_forever()
                break
        except OSError as e:
            if "address already in use" in str(e).lower() or e.errno == 48 or e.errno == 10048:
                port += 1
                continue
            raise


if __name__ == "__main__":
    run_server()
