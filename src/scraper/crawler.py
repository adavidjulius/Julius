"""High-level scraper orchestrator.

Library:
    from src.scraper import Scraper
    async with Scraper() as s:
        result = await s.crawl(url, follow='next', max_pages=10)
        await s.direct_download(url, 'out.bin')

CLI:
    python -m src.scraper.crawler <url> [--pages N] [--follow next|prev|both]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from .pagination import find_next_url, find_prev_url
from .network_capture import NetworkCapture, CapturedRequest
from .direct_download import DirectDownloader, capture_session_from_context

logger = logging.getLogger(__name__)
FollowMode = Literal['next', 'prev', 'both']


@dataclass
class Page:
    url: str
    title: str
    html: str
    text: str
    fetched_at: str
    screenshot_path: str | None = None
    captured_requests: int = 0


@dataclass
class CrawlResult:
    start_url: str
    pages: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    api_endpoints: list = field(default_factory=list)
    download_candidates: list = field(default_factory=list)
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            'start_url': self.start_url,
            'page_count': len(self.pages),
            'duration_s': self.duration_s,
            'pages': [
                {'url': p.url, 'title': p.title, 'fetched_at': p.fetched_at,
                 'html_bytes': len(p.html), 'text_bytes': len(p.text),
                 'screenshot': p.screenshot_path}
                for p in self.pages
            ],
            'api_endpoints': [
                {'url': r.url, 'method': r.method, 'resource_type': r.resource_type,
                 'status': r.status, 'content_type': r.content_type}
                for r in self.api_endpoints
            ],
            'download_candidates': [
                {'url': r.url, 'method': r.method, 'status': r.status,
                 'content_type': r.content_type}
                for r in self.download_candidates
            ],
            'errors': self.errors,
        }


class Scraper:
    def __init__(self, headless: bool = True, out_dir: Path | str = 'scraper_out',
                 user_agent: str | None = None, timeout_ms: int = 30000) -> None:
        self.headless = headless
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser = None
        self._context = None
        self.capture = NetworkCapture()

    async def __aenter__(self) -> 'Scraper':
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            user_agent=self.user_agent,
            viewport={'width': 1440, 'height': 900},
            ignore_https_errors=False,
        )

    async def stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as exc:
            logger.debug('stop: %s', exc)

    async def _grab(self, url, screenshot):
        page = await self._context.new_page()
        self.capture.attach(page)
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout_ms)
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)
            except PWTimeout:
                pass
            title = await page.title()
            html = await page.content()
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            shot = None
            if screenshot:
                stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
                shot_path = self.out_dir / f'shot_{stamp}.png'
                try:
                    await page.screenshot(path=str(shot_path), full_page=True)
                    shot = str(shot_path)
                except Exception as exc:
                    logger.warning('screenshot failed: %s', exc)
            return Page(url=page.url, title=title, html=html, text=text,
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                        screenshot_path=shot,
                        captured_requests=len(self.capture.requests))
        finally:
            await page.close()

    async def crawl(self, start_url, follow='next', max_pages=10,
                    screenshot=False, stop_on_cycle=True):
        result = CrawlResult(start_url=start_url)
        started = datetime.now(timezone.utc)
        visited = set()
        queue = [start_url]
        while queue and len(result.pages) < max_pages:
            url = queue.pop(0)
            if stop_on_cycle and url in visited:
                continue
            visited.add(url)
            try:
                p = await self._grab(url, screenshot=screenshot)
                result.pages.append(p)
                logger.info('page %d: %s', len(result.pages), p.url)
            except Exception as exc:
                logger.warning('fetch failed for %s: %s', url, exc)
                result.errors.append({'url': url, 'error': str(exc)})
                continue
            page = await self._context.new_page()
            try:
                await page.goto(p.url, wait_until='domcontentloaded', timeout=self.timeout_ms)
                next_url = None
                prev_url = None
                if follow in ('next', 'both'):
                    next_url = await find_next_url(page)
                if follow in ('prev', 'both'):
                    prev_url = await find_prev_url(page)
                for candidate in (next_url, prev_url):
                    if candidate and candidate not in visited and candidate not in queue:
                        queue.append(candidate)
            except Exception as exc:
                logger.debug('pagination discovery failed: %s', exc)
            finally:
                await page.close()
        result.api_endpoints = self.capture.api_candidates()
        result.download_candidates = self.capture.download_candidates()
        result.duration_s = (datetime.now(timezone.utc) - started).total_seconds()
        return result

    async def analyze_endpoints(self):
        return self.capture.api_candidates()

    async def direct_download(self, url, dest, extra_headers=None):
        cookies, ua = await capture_session_from_context(self._context)
        headers = dict(extra_headers or {})
        headers.setdefault('User-Agent', ua)
        async with DirectDownloader(cookies=cookies, extra_headers=headers) as dl:
            return await dl.download_file(url, Path(dest))

    def save_report(self, result, name='report'):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        out = self.out_dir / f'{name}_{stamp}.json'
        out.write_text(json.dumps(result.to_dict(), indent=2))
        pages_dir = self.out_dir / f'pages_{stamp}'
        pages_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(result.pages, 1):
            (pages_dir / f'{i:03d}.html').write_text(p.html)
            (pages_dir / f'{i:03d}.txt').write_text(p.text)
        logger.info('report saved: %s (pages: %s)', out, pages_dir)
        return out


async def _main():
    ap = argparse.ArgumentParser(description='Julius web scraper')
    ap.add_argument('url')
    ap.add_argument('--pages', type=int, default=10)
    ap.add_argument('--follow', choices=['next', 'prev', 'both'], default='next')
    ap.add_argument('--out', default='scraper_out')
    ap.add_argument('--screenshot', action='store_true')
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--download')
    ap.add_argument('--download-to', default='scraper_out/download.bin')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    async with Scraper(headless=not args.headed, out_dir=args.out) as s:
        result = await s.crawl(args.url, follow=args.follow,
                               max_pages=args.pages, screenshot=args.screenshot)
        report = s.save_report(result)
        print('pages:', len(result.pages), 'endpoints:', len(result.api_endpoints), 'errors:', len(result.errors))
        print('report:', report)
        if result.api_endpoints:
            print('top API endpoints:')
            for r in result.api_endpoints[:15]:
                print('  ', r.method, r.status, r.url[:140])
        if args.download:
            p = await s.direct_download(args.download, args.download_to)
            print('downloaded:', p)


if __name__ == '__main__':
    asyncio.run(_main())
