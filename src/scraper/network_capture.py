"""Capture network traffic during a Playwright session.

Attaches to a Playwright Page and records requests/responses so we can
see which backend endpoints the site uses — the first step toward talking
to the server directly instead of driving the UI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CapturedRequest:
    url: str
    method: str
    resource_type: str
    headers: dict = field(default_factory=dict)
    post_data: str | None = None
    status: int | None = None
    response_headers: dict = field(default_factory=dict)
    content_type: str | None = None
    response_body_preview: str | None = None


class NetworkCapture:
    """Record all requests/responses on a page. Call `attach(page)` once."""

    def __init__(self, json_preview_chars: int = 4000) -> None:
        self.requests: list[CapturedRequest] = []
        self._pending: dict[Any, CapturedRequest] = {}
        self._json_preview_chars = json_preview_chars

    def attach(self, page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _on_request(self, request) -> None:
        try:
            self._pending[id(request)] = CapturedRequest(
                url=request.url,
                method=request.method,
                resource_type=request.resource_type,
                headers=dict(request.headers),
                post_data=request.post_data,
            )
        except Exception as exc:
            logger.debug("request capture failed: %s", exc)

    async def _on_response(self, response) -> None:
        try:
            request = response.request
            cap = self._pending.pop(id(request), None)
            if cap is None:
                cap = CapturedRequest(
                    url=request.url,
                    method=request.method,
                    resource_type=request.resource_type,
                )
            cap.status = response.status
            cap.response_headers = dict(response.headers)
            cap.content_type = response.headers.get("content-type", "")
            if "json" in (cap.content_type or ""):
                try:
                    body = await response.text()
                    cap.response_body_preview = body[: self._json_preview_chars]
                except Exception as exc:
                    logger.debug("body preview failed: %s", exc)
            self.requests.append(cap)
        except Exception as exc:
            logger.debug("response capture failed: %s", exc)

    def api_candidates(self) -> list[CapturedRequest]:
        """Filter to XHR/fetch or JSON responses — likely the real backend."""
        out: list[CapturedRequest] = []
        for r in self.requests:
            is_xhr = r.resource_type in ("xhr", "fetch")
            is_json = bool(r.content_type and "json" in r.content_type)
            if is_xhr or is_json:
                out.append(r)
        return out

    def download_candidates(self) -> list[CapturedRequest]:
        """Responses that look like file downloads (non-HTML, non-JS/CSS)."""
        skip = ("text/html", "application/javascript", "text/css", "image/")
        out: list[CapturedRequest] = []
        for r in self.requests:
            ct = (r.content_type or "").lower()
            if not ct:
                continue
            if any(ct.startswith(s) for s in skip):
                continue
            if r.status and 200 <= r.status < 300:
                out.append(r)
        return out
