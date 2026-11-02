"""
Julius Browser Portal (Obsolete Web Chat Login Cleaned).

Previously provided interactive Chromium session login for consumer web chat interfaces.
With the migration to NVIDIA NIM Direct API, web chat browser login is obsolete.
"""

from __future__ import annotations

import logging
from typing import Any
from aiohttp import web

logger = logging.getLogger(__name__)

PORTAL_PROVIDERS = {
    "nvidia": "https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b",
    "deepseek": "https://api.deepseek.com",
    "chatgpt": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "grok": "https://api.x.ai/v1",
    "perplexity": "https://api.perplexity.ai",
}


async def get_portal_client(app: web.Application, provider: str = "nvidia") -> Any:
    """Obsolete: WebLLMClient browser session login is no longer required."""
    return None


async def browser_portal_handler(request: web.Request) -> web.Response:
    """Serve informative status page confirming Direct API architecture."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Julius — Direct API Architecture</title>
    <style>
        :root {
            --bg: #090d16;
            --card-bg: #131b2e;
            --border: #1e293b;
            --accent: #38bdf8;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --success: #4ade80;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 24px;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 36px;
            max-width: 600px;
            text-align: center;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }
        .badge {
            display: inline-block;
            background: rgba(74, 222, 128, 0.15);
            color: var(--success);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 20px;
        }
        h1 { font-size: 24px; margin-bottom: 12px; }
        p { color: var(--text-muted); font-size: 15px; line-height: 1.6; margin-bottom: 24px; }
        .details {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            text-align: left;
            font-size: 13px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: #cbd5e1;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">Direct API Mode Active</div>
        <h1>Browser Login Obsolete</h1>
        <p>
            Julius has migrated from headless browser web scraping to direct, authenticated API integration.
            Browser login sessions via Playwright are obsolete and no longer required.
        </p>
        <div class="details">
            <div><strong>Active Model:</strong> NVIDIA Nemotron-3 Ultra 550B</div>
            <div><strong>Protocol:</strong> Direct REST / SSE Streaming</div>
            <div><strong>Rate Limiter:</strong> 40 RPM Intelligent Spacing</div>
            <div><strong>Browser Automation:</strong> Retained exclusively for web navigation tools</div>
        </div>
    </div>
</body>
</html>
"""
    return web.Response(text=html, content_type="text/html")


async def api_browser_portal_handler(request: web.Request) -> web.Response:
    """Return JSON status indicating direct API operation."""
    provider = request.query.get("provider", "nvidia")
    return web.json_response({
        "active": True,
        "direct_api": True,
        "provider": provider,
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "logged_in": True,
        "message": "Direct API active; browser session login is obsolete.",
    })


async def api_browser_screenshot_handler(request: web.Request) -> web.Response:
    """Obsolete: Screenshots of web chat sessions are no longer captured."""
    return web.json_response({
        "success": False,
        "error": "Browser session screenshots are obsolete in Direct API mode.",
    }, status=410)


async def api_browser_action_handler(request: web.Request) -> web.Response:
    """Obsolete: Interactive browser actions on web chats are no longer accepted."""
    return web.json_response({
        "success": True,
        "message": "Interactive browser actions on web chat interfaces are obsolete in Direct API mode.",
    })
