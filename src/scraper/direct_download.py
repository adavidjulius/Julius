"""Direct HTTP download using httpx, replaying a captured browser session.

Once we've seen how the site talks to its server (endpoints, cookies, UA,
required headers), we can skip the browser and download directly.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


class DirectDownloader:
    """Async httpx wrapper that carries cookies/headers from a browser session."""

    def __init__(
        self,
        cookies: dict | None = None,
        extra_headers: dict | None = None,
        timeout: float = 60.0,
    ) -> None:
        headers = dict(DEFAULT_HEADERS)
        if extra_headers:
            headers.update({k: v for k, v in extra_headers.items() if v})
        self._client = httpx.AsyncClient(
            headers=headers,
            cookies=cookies or {},
            follow_redirects=True,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DirectDownloader":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def fetch(self, url: str, headers: dict | None = None) -> httpx.Response:
        logger.info("GET %s", url)
        response = await self._client.get(url, headers=headers)
        return response

    async def fetch_json(self, url: str, headers: dict | None = None) -> dict:
        response = await self.fetch(url, headers=headers)
        response.raise_for_status()
        return response.json()

    async def download_file(
        self,
        url: str,
        dest: Path,
        headers: dict | None = None,
        chunk_size: int = 65536,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size):
                    fh.write(chunk)
        logger.info("saved %s (%d bytes)", dest, dest.stat().st_size)
        return dest


async def capture_session_from_context(context) -> tuple[dict, str]:
    """Return (cookie_dict, user_agent) from a live Playwright BrowserContext."""
    cookies = await context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    try:
        ua = await context.pages[0].evaluate("navigator.userAgent")
    except Exception:
        ua = DEFAULT_HEADERS["User-Agent"]
    return cookie_dict, ua
