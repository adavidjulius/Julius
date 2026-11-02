"""Lightweight prompt linter for typo resilience and input normalization.

Fixes common typos, normalizes unicode, and cleans whitespace before
the user's task enters the main agent loop. This is a zero-latency
dictionary-based approach — no LLM call required.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# ── Common typo dictionary ────────────────────────────────────────────────────
# Maps lowercase misspellings → correct form.
# These are curated from real developer inputs and common keyboard slip patterns.

COMMON_TYPOS: dict[str, str] = {
    # General English typos
    'teh': 'the',
    'hte': 'the',
    'adn': 'and',
    'nad': 'and',
    'wiht': 'with',
    'waht': 'what',
    'taht': 'that',
    'tahn': 'than',
    'thier': 'their',
    'becuase': 'because',
    'beacuse': 'because',
    'definately': 'definitely',
    'seperate': 'separate',
    'occured': 'occurred',
    'occurence': 'occurrence',
    'recieve': 'receive',
    'acheive': 'achieve',
    'untill': 'until',
    'doesnt': "doesn't",
    'dont': "don't",
    'cant': "can't",
    'wont': "won't",
    'isnt': "isn't",
    'wasnt': "wasn't",
    'didnt': "didn't",
    'shouldnt': "shouldn't",
    'couldnt': "couldn't",
    'wouldnt': "wouldn't",

    # Developer/coding-specific typos
    'anlayse': 'analyse',
    'anaylse': 'analyse',
    'analize': 'analyse',
    'analzye': 'analyse',
    'propmt': 'prompt',
    'pormpt': 'prompt',
    'pormt': 'prompt',
    'propmts': 'prompts',
    'fucntion': 'function',
    'funciton': 'function',
    'funtion': 'function',
    'fucntion': 'function',
    'fucntions': 'functions',
    'varaible': 'variable',
    'varialbe': 'variable',
    'variabel': 'variable',
    'refactor': 'refactor',
    'refacor': 'refactor',
    'refatcor': 'refactor',
    'implment': 'implement',
    'implmenet': 'implement',
    'impelment': 'implement',
    'implemenation': 'implementation',
    'implementaiton': 'implementation',
    'depednency': 'dependency',
    'dependancy': 'dependency',
    'depdendency': 'dependency',
    'confgiuration': 'configuration',
    'configuraion': 'configuration',
    'configuraiton': 'configuration',
    'repositroy': 'repository',
    'repostiory': 'repository',
    'initalize': 'initialize',
    'initailize': 'initialize',
    'initializaiton': 'initialization',
    'datbase': 'database',
    'databse': 'database',
    'databaes': 'database',
    'endpoing': 'endpoint',
    'endpiont': 'endpoint',
    'authetication': 'authentication',
    'authentcation': 'authentication',
    'authetnication': 'authentication',
    'parametr': 'parameter',
    'paramter': 'parameter',
    'arguemnt': 'argument',
    'agument': 'argument',
    'reutrn': 'return',
    'retrun': 'return',
    'reuslt': 'result',
    'resutl': 'result',
    'modle': 'model',
    'moduel': 'module',
    'directroy': 'directory',
    'direcotry': 'directory',
    'creaet': 'create',
    'craete': 'create',
    'delte': 'delete',
    'deleet': 'delete',
    'udpate': 'update',
    'upadte': 'update',
    'updaet': 'update',
    'insatll': 'install',
    'intall': 'install',
    'isntall': 'install',
    'depdencies': 'dependencies',
    'dependecies': 'dependencies',
    'tempalte': 'template',
    'templaet': 'template',
    'compoennt': 'component',
    'componet': 'component',
    'strucutre': 'structure',
    'struture': 'structure',
    'sytax': 'syntax',
    'syntaz': 'syntax',
    'debugg': 'debug',
    'eroor': 'error',
    'erorr': 'error',
}


# ── Unicode normalization map ─────────────────────────────────────────────────

_UNICODE_QUOTES = {
    '\u2018': "'",   # '
    '\u2019': "'",   # '
    '\u201C': '"',   # "
    '\u201D': '"',   # "
    '\u2013': '-',   # –
    '\u2014': '--',  # —
    '\u2026': '...', # …
}


def _normalize_unicode(text: str) -> str:
    """Replace smart quotes and other unicode punctuation with ASCII equivalents."""
    for char, replacement in _UNICODE_QUOTES.items():
        text = text.replace(char, replacement)
    # Normalize remaining unicode to NFC form
    return unicodedata.normalize('NFC', text)


def _fix_typos(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Apply word-level typo corrections. Returns (corrected_text, list_of_corrections)."""
    corrections: list[tuple[str, str]] = []

    def _replace_word(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if lower in COMMON_TYPOS:
            corrected = COMMON_TYPOS[lower]
            # Preserve original capitalization pattern
            if word[0].isupper():
                corrected = corrected[0].upper() + corrected[1:]
            if word.isupper():
                corrected = corrected.upper()
            corrections.append((word, corrected))
            return corrected
        return word

    # Match word boundaries but skip things inside code blocks, paths, and quoted strings
    # Simple heuristic: only correct words that are purely alphabetical
    corrected = re.sub(r'\b[A-Za-z]+\b', _replace_word, text)
    return corrected, corrections


def _normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving single newlines."""
    # Collapse multiple spaces to one
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Collapse 3+ newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def lint_prompt(raw: str) -> str:
    """
    Normalize and clean a user prompt before it enters the agent loop.

    Applies:
    1. Unicode normalization (smart quotes → ASCII)
    2. Word-level typo correction
    3. Whitespace normalization
    4. Strips stray cursor glyphs (█ \u2588) from copy/paste or terminal input
    """
    if not raw or not raw.strip():
        return raw

    # Strip stray terminal block/cursor characters
    clean_raw = raw.replace('█', '').replace('\u2588', '').strip()
    if not clean_raw:
        clean_raw = raw.strip()

    # Step 1: Unicode normalization
    text = _normalize_unicode(clean_raw)

    # Step 2: Typo correction
    text, corrections = _fix_typos(text)

    # Step 3: Whitespace normalization
    text = _normalize_whitespace(text)

    # Log corrections if any were made
    if corrections:
        correction_log = ', '.join(f'"{orig}" → "{fixed}"' for orig, fixed in corrections)
        logger.info(f'Prompt linter applied {len(corrections)} correction(s): {correction_log}')

    return text
