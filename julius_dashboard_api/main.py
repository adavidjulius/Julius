from __future__ import annotations

import asyncio
import os
import logging
import time
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from src.search_connector import SearXNGClient
from src.prompt_assembler import assemble_prompt
from src.citation_extractor import extract_citation_map
from src.memory import WorkingStateManager

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("julius_dashboard_api")

app = FastAPI(title="Julius RAG Grounding Dashboard API")

# Configure CORS — Finding #1: never use wildcard origins with credentials
ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Finding #2: enforce strict payload size cap
MAX_QUERY_CHARS = int(os.getenv("MAX_QUERY_CHARS", "8000"))


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS)

    @field_validator("query")
    @classmethod
    def validate_query_size(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Query cannot be empty or whitespace-only")
        return stripped


class ChatResponse(BaseModel):
    answer_text: str
    sources: dict
    cited_order: list[int]

# Initialize SearXNG client
searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080")
searxng_client = SearXNGClient(base_url=searxng_url)

def get_llm_client():
    """Returns (AsyncOpenAI client, model_name) based on available environment variables."""
    if AsyncOpenAI is None:
        return None, None

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if deepseek_key:
        base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        return AsyncOpenAI(api_key=deepseek_key, base_url=base_url), "deepseek-chat"
    elif openai_key:
        base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        return AsyncOpenAI(api_key=openai_key, base_url=base_url), "gpt-4o-mini"
    
    return None, None


from typing import Optional

@app.get("/api/health")
def health():
    return {"status": "ok", "searxng_url": searxng_url}

@app.get("/api/resumption/tasks")
def get_resumption_tasks(project_id: Optional[str] = None):
    """Stage 5: Resume indicator endpoint for Task/Project Dashboard screen."""
    workspace = os.getenv("JULIUS_WORKSPACE", ".")
    mgr = WorkingStateManager(workspace)
    pid = project_id or str(Path(workspace).resolve())
    active_tasks = mgr.get_active_tasks(pid)
    res = []
    for t in active_tasks:
        d = t.to_dict()
        d["likely_abandoned"] = mgr.is_likely_abandoned(t)
        res.append(d)
    return {"project_id": pid, "active_tasks": res, "total_active": len(res)}


def needs_search(query: str) -> bool:
    """Decision point for query search grounding. Simplest default is always search."""
    return True


# ── Finding #6: simple in-memory rate limiter ─────────────────────────────────
_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))  # requests per window per IP


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is within the rate limit, False otherwise."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if t > window_start]
    if len(_rate_limits[client_ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[client_ip].append(now)
    return True


LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    # Finding #6: enforce rate limiting
    client_ip = req.client.host if req.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")

    query = request.query  # already stripped and validated by Pydantic
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    logger.info("Received query: %s", query)

    # 1. Query SearXNG client (if needed)
    search_results = []
    if needs_search(query):
        start_time = time.perf_counter()
        search_results = await searxng_client.search(query)
        latency = time.perf_counter() - start_time
        logger.info(
            "Search for query=%r returned %d results in %.4f seconds (latency)",
            query, len(search_results), latency
        )
    else:
        logger.info("Search skipped for query=%r", query)

    # 2. Assemble prompt context
    messages = assemble_prompt(query, search_results)

    # 3. Call LLM
    client, model = get_llm_client()
    if not client:
        # Fallback response for offline / keyless testing
        logger.warning("No API keys found for LLM. Returning mocked grounded response.")
        fallback_answer = (
            f"Here is a mock response grounding search results for '{query}'. "
            "To get a real answer, please set DEEPSEEK_API_KEY or OPENAI_API_KEY in your environment. "
            "According to our search results [1], we found relevant information. "
            "Another source confirms this statement [2]."
        )
        # Extract citations
        citation_data = extract_citation_map(fallback_answer, search_results)
        return ChatResponse(
            answer_text=citation_data["answer_text"],
            sources=citation_data["sources"],
            cited_order=citation_data["cited_order"]
        )

    # Finding #4: enforce timeout on LLM call
    try:
        completion = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        answer_text = completion.choices[0].message.content
        logger.info("LLM generated response successfully")
    except asyncio.TimeoutError:
        logger.error("LLM call timed out after %ds", LLM_TIMEOUT_SECONDS)
        raise HTTPException(status_code=504, detail="Model response timed out. Please retry.")
    except Exception as e:
        # Finding #3: never leak raw exception details to clients
        error_id = str(uuid.uuid4())[:8]
        logger.error("LLM call failed [%s]: %s", error_id, e, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Upstream model service unavailable. Reference: {error_id}"
        )

    # 4. Extract citations
    citation_data = extract_citation_map(answer_text, search_results)

    return ChatResponse(
        answer_text=citation_data["answer_text"],
        sources=citation_data["sources"],
        cited_order=citation_data["cited_order"]
    )
