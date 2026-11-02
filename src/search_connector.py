# search_connector.py
import httpx
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("search_connector")


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


class SearchConnectorError(Exception):
    """Raised only for logging/telemetry — never propagated raw to the caller."""


class SearXNGClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout_seconds: float = 4.0,
        max_results: Optional[int] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    async def search(self, query: str) -> list[SearchResult]:
        """
        Executes a search against SearXNG and returns a sanitized,
        top-N list of SearchResult objects. Never raises — on any
        failure it returns an empty list so the caller can decide
        how to degrade gracefully (e.g. answer without grounding).
        """
        if not query or not query.strip():
            return []

        params = {"q": query.strip(), "format": "json"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/search", params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            logger.warning("SearXNG timeout for query=%r", query)
            return []
        except httpx.HTTPStatusError as e:
            logger.warning("SearXNG HTTP error %s for query=%r", e.response.status_code, query)
            return []
        except (ValueError, httpx.RequestError) as e:
            logger.warning("SearXNG malformed response/connection error: %s", e)
            return []

        return self._parse_and_sanitize(payload)

    def _parse_and_sanitize(self, payload: dict) -> list[SearchResult]:
        raw_results = payload.get("results", [])
        if self.max_results is not None:
            raw_results = raw_results[: self.max_results]
        cleaned: list[SearchResult] = []

        for item in raw_results:
            title = self._sanitize(item.get("title", ""))
            url = item.get("url", "").strip()
            content = self._sanitize(item.get("content", ""))

            if not url or not title:
                continue  # skip malformed entries instead of crashing

            cleaned.append(SearchResult(title=title, url=url, content=content))

        return cleaned

    @staticmethod
    def _sanitize(text: str) -> str:
        if not text:
            return ""
        # Strip control chars / collapse whitespace / cap length defensively
        text = " ".join(text.split())
        return text[:500]
