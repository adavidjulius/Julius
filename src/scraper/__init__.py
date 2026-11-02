"""src.scraper — general-purpose web scraper built on Playwright + httpx.

Public API:
    Scraper          — orchestrator: crawl, paginate, capture network, direct download
    CrawlResult      — list of pages + discovered endpoints + errors
    Page             — one captured page snapshot
    find_next_url    — pagination helper (next)
    find_prev_url    — pagination helper (previous)
    NetworkCapture   — request/response interceptor
    DirectDownloader — httpx-based direct downloader (bypasses the browser)
"""

from .crawler import Scraper, CrawlResult, Page
from .pagination import find_next_url, find_prev_url
from .network_capture import NetworkCapture, CapturedRequest
from .direct_download import DirectDownloader

__all__ = [
    "Scraper", "CrawlResult", "Page",
    "find_next_url", "find_prev_url",
    "NetworkCapture", "CapturedRequest",
    "DirectDownloader",
]
