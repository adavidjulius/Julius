"""
Julius Live Internet Search & Real-Time Context Engine
═════════════════════════════════════════════════════
Provides real-time web grounding, temporal anchors (current date & time),
and live information retrieval via Wikipedia and DuckDuckGo for Julius.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("JuliusLiveSearch")


def get_current_datetime_str() -> str:
    """Return formatted real-world date and time string."""
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y at %I:%M %p")


def get_current_year() -> int:
    return datetime.datetime.now().year


def search_wikipedia_live(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Query Wikipedia API and REST endpoints for live real-time encyclopedia summaries."""
    results: List[Dict[str, str]] = []
    try:
        url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
            + urllib.parse.quote(query)
            + "&format=json&utf8=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "JuliusStudyBrain/2.0 (academic; live-search)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("query", {}).get("search", [])

            for h in hits[:max_results]:
                title = h.get("title", "")
                snippet = re.sub(r"<[^>]+>", "", h.get("snippet", "")).strip()
                if not title:
                    continue

                # Fetch full summary extract
                clean_slug = urllib.parse.quote(title.replace(" ", "_"))
                sum_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_slug}"
                sum_req = urllib.request.Request(sum_url, headers={"User-Agent": "JuliusStudyBrain/2.0"})
                extract = ""
                try:
                    with urllib.request.urlopen(sum_req, timeout=4) as sum_resp:
                        sum_data = json.loads(sum_resp.read().decode("utf-8"))
                        extract = sum_data.get("extract", "")
                except Exception:
                    extract = snippet

                results.append({
                    "title": title,
                    "snippet": extract or snippet,
                    "source": "Wikipedia (Live)",
                })
    except Exception as exc:
        logger.warning(f"Wikipedia live search failed: {exc}")

    return results


def search_duckduckgo_live(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Scrape live search results from DuckDuckGo HTML."""
    results: List[Dict[str, str]] = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Extract links and snippets
            matches = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
            for m in matches[:max_results]:
                clean = re.sub(r"<[^>]+>", "", m).strip()
                if clean and len(clean) > 20:
                    results.append({
                        "title": query,
                        "snippet": clean,
                        "source": "Web Search (Live)",
                    })
    except Exception as exc:
        logger.warning(f"DuckDuckGo live search failed: {exc}")

    return results


def perform_live_search(query: str) -> List[Dict[str, str]]:
    """Aggregate search results from Wikipedia and live web."""
    combined: List[Dict[str, str]] = []
    wiki_hits = search_wikipedia_live(query, max_results=2)
    combined.extend(wiki_hits)

    # If wiki hits are sparse or query has time-sensitive words, also query web
    web_hits = search_duckduckgo_live(query, max_results=3)
    for w in web_hits:
        # Avoid duplicate snippets
        if not any(w["snippet"][:40].lower() in c["snippet"].lower() for c in combined):
            combined.append(w)

    return combined


def format_search_context(query: str, hits: List[Dict[str, str]]) -> str:
    """Format live search results into a clean context string for LLM grounding."""
    dt_str = get_current_datetime_str()
    lines = [f"[Live Internet & Knowledge Search Grounding — {dt_str}]:"]
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. [{h['title']}] ({h['source']}): {h['snippet']}")
    return "\n".join(lines)
