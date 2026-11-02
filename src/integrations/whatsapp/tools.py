"""
Julius WhatsApp Integration — System Tools Layer.

Deterministic tools for exact time (Asia/Kolkata and global timezones),
live web search, and outside world grounding.
Never hallucinates date, time, or outside factual information.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LOCATION_TIMEZONES: Dict[str, str] = {
    # Japan / Asia
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "kyoto": "Asia/Tokyo",
    "osaka": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "south korea": "Asia/Seoul",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "taiwan": "Asia/Taipei",
    "taipei": "Asia/Taipei",
    "singapore": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur",
    "kuala lumpur": "Asia/Kuala_Lumpur",
    "bangkok": "Asia/Bangkok",
    "thailand": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta",
    "indonesia": "Asia/Jakarta",
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "abu dhabi": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh",
    "riyadh": "Asia/Riyadh",
    "doha": "Asia/Qatar",
    "qatar": "Asia/Qatar",
    "kuwait": "Asia/Kuwait",
    "israel": "Asia/Jerusalem",
    "jerusalem": "Asia/Jerusalem",
    "tel aviv": "Asia/Jerusalem",

    # India / South Asia
    "india": "Asia/Kolkata",
    "chennai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "new delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata",
    "colombo": "Asia/Colombo",
    "sri lanka": "Asia/Colombo",
    "dhaka": "Asia/Dhaka",
    "bangladesh": "Asia/Dhaka",
    "kathmandu": "Asia/Kathmandu",
    "nepal": "Asia/Kathmandu",

    # UK & Europe
    "london": "Europe/London",
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "england": "Europe/London",
    "great britain": "Europe/London",
    "paris": "Europe/Paris",
    "france": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "frankfurt": "Europe/Berlin",
    "munich": "Europe/Berlin",
    "rome": "Europe/Rome",
    "italy": "Europe/Rome",
    "milan": "Europe/Rome",
    "madrid": "Europe/Madrid",
    "spain": "Europe/Madrid",
    "barcelona": "Europe/Madrid",
    "amsterdam": "Europe/Amsterdam",
    "netherlands": "Europe/Amsterdam",
    "brussels": "Europe/Brussels",
    "belgium": "Europe/Brussels",
    "zurich": "Europe/Zurich",
    "geneva": "Europe/Zurich",
    "switzerland": "Europe/Zurich",
    "vienna": "Europe/Vienna",
    "austria": "Europe/Vienna",
    "stockholm": "Europe/Stockholm",
    "sweden": "Europe/Stockholm",
    "oslo": "Europe/Oslo",
    "norway": "Europe/Oslo",
    "copenhagen": "Europe/Copenhagen",
    "denmark": "Europe/Copenhagen",
    "helsinki": "Europe/Helsinki",
    "finland": "Europe/Helsinki",
    "dublin": "Europe/Dublin",
    "ireland": "Europe/Dublin",
    "moscow": "Europe/Moscow",
    "russia": "Europe/Moscow",
    "athens": "Europe/Athens",
    "greece": "Europe/Athens",
    "istanbul": "Europe/Istanbul",
    "turkey": "Europe/Istanbul",

    # Americas
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "ny": "America/New_York",
    "washington": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "atlanta": "America/New_York",
    "chicago": "America/Chicago",
    "dallas": "America/Chicago",
    "houston": "America/Chicago",
    "texas": "America/Chicago",
    "denver": "America/Denver",
    "colorado": "America/Denver",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "california": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "las vegas": "America/Los_Angeles",
    "toronto": "America/Toronto",
    "canada": "America/Toronto",
    "vancouver": "America/Vancouver",
    "montreal": "America/Toronto",
    "ottawa": "America/Toronto",
    "mexico city": "America/Mexico_City",
    "mexico": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    "brazil": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "argentina": "America/Argentina/Buenos_Aires",

    # Australia / Pacific
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "australia": "Australia/Sydney",
    "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth",
    "auckland": "Pacific/Auckland",
    "new zealand": "Pacific/Auckland",

    # Africa
    "cairo": "Africa/Cairo",
    "egypt": "Africa/Cairo",
    "johannesburg": "Africa/Johannesburg",
    "south africa": "Africa/Johannesburg",
    "nairobi": "Africa/Nairobi",
    "kenya": "Africa/Nairobi",
    "lagos": "Africa/Lagos",
    "nigeria": "Africa/Lagos",
}


def get_current_datetime(timezone_name: str = "Asia/Kolkata") -> Dict[str, Any]:
    """
    Return exact current date, time, weekday, and timestamp in any specified timezone.
    Prevents the LLM from hallucinating date or time.
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone_name)
        now = datetime.datetime.now(tz)
    except Exception:
        # Fallback to UTC + 5:30 if zoneinfo is unavailable
        offset = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(offset)

    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday = weekday_names[now.weekday()]
    tz_abbr = now.strftime("%Z") or timezone_name.split("/")[-1]

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "time_12h": now.strftime("%I:%M %p"),
        "hour": now.hour,
        "minute": now.minute,
        "weekday": weekday,
        "timezone": timezone_name,
        "tz_abbr": tz_abbr,
        "unix_timestamp": now.timestamp(),
        "formatted": f"{now.strftime('%I:%M %p')} {tz_abbr} ({weekday}, {now.strftime('%B %d, %Y')})",
    }


def get_time_for_location(query: str) -> Optional[Dict[str, Any]]:
    """
    Detect if query is asking for the time in a specific city/country/region
    and return the exact verified datetime.
    """
    if not query:
        return None
    q_low = query.lower()

    # Sort location keys by length descending to match multi-word locations first (e.g. "new york" before "york")
    sorted_locs = sorted(LOCATION_TIMEZONES.keys(), key=lambda k: len(k), reverse=True)
    for loc in sorted_locs:
        # Word boundary match
        pattern = rf"\b{re.escape(loc)}\b"
        if re.search(pattern, q_low):
            tz_name = LOCATION_TIMEZONES[loc]
            dt = get_current_datetime(tz_name)
            dt["location_matched"] = loc.title()
            return dt

    return None


def search_wikipedia(query: str) -> Optional[str]:
    """
    Search Wikipedia for entity definitions, people, places, concepts.
    Returns clean factual summary text without HTML.
    """
    if not query:
        return None
    try:
        clean_q = query.strip()
        # 1. Search for title
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q)}&format=json"
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "JuliusBot/1.0 (contact@julius.ai)"},
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        hits = data.get("query", {}).get("search", [])
        if not hits:
            return None
        title = hits[0].get("title", "")
        if not title:
            return None

        # 2. Fetch page summary
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        req2 = urllib.request.Request(
            summary_url,
            headers={"User-Agent": "JuliusBot/1.0 (contact@julius.ai)"},
        )
        with urllib.request.urlopen(req2, timeout=5.0) as resp2:
            s_data = json.loads(resp2.read().decode("utf-8"))
        extract = s_data.get("extract", "")
        if extract:
            return f"**{title}**: {extract}"
    except Exception as e:
        logger.debug("[TOOLS] Wikipedia search error: %s", e)
    return None


def web_search(query: str, max_results: int = 3) -> str:
    """
    Perform a live web/internet search.
    First checks Wikipedia for factual questions, then falls back to DuckDuckGo/general search.
    """
    if not query:
        return "No query provided."

    clean_q = query.strip()

    # 1. Check if asking for time in a location
    loc_time = get_time_for_location(clean_q)
    if loc_time:
        return f"Verified time in {loc_time['location_matched']}: {loc_time['formatted']}."

    # 2. Try Wikipedia summary for general knowledge/people/terms
    wiki_res = search_wikipedia(clean_q)
    if wiki_res:
        return wiki_res

    # 3. DuckDuckGo fallback
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        snippets = re.findall(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
        if snippets:
            clean_snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets[:max_results]]
            return "\n\n".join(clean_snippets)
    except Exception as e:
        logger.debug("[TOOLS] web_search exception for '%s': %s", query, e)

    return f"Live search results for '{clean_q}' were inconclusive or timed out."


def fetch_url(url: str, max_bytes: int = 10000) -> str:
    """Fetch text from a public web page."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "JuliusBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            content = resp.read(max_bytes).decode("utf-8", errors="ignore")
        text = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1500]
    except Exception as e:
        logger.debug("[TOOLS] fetch_url exception: %s", e)
        return f"Could not fetch URL: {e}"
