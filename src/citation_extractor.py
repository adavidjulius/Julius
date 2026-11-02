# citation_extractor.py
import re
from .search_connector import SearchResult

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_citation_map(answer_text: str, results: list[SearchResult]) -> dict:
    """
    Scans the model's answer for [n] markers, and returns a payload
    the frontend can use to render clickable citation cards —
    without duplicating source data for every marker occurrence.
    """
    cited_indices = sorted({int(m) for m in CITATION_PATTERN.findall(answer_text)})

    sources = {}
    valid_indices = []
    for idx in cited_indices:
        if 1 <= idx <= len(results):
            r = results[idx - 1]
            sources[idx] = {"title": r.title, "url": r.url, "snippet": r.content}
            valid_indices.append(idx)

    return {
        "answer_text": answer_text,
        "sources": sources,          # {1: {...}, 2: {...}}
        "cited_order": valid_indices,
    }
