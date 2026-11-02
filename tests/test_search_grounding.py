import pytest
from src.search_connector import SearXNGClient, SearchResult
from src.prompt_assembler import assemble_prompt, build_context_block
from src.citation_extractor import extract_citation_map

def test_prompt_assembler_empty_results():
    results = []
    block = build_context_block(results)
    assert block == "No search results were available for this query."
    
    prompt = assemble_prompt("What is Google?", results)
    assert len(prompt) == 2
    assert "No search results were available for this query." in prompt[1]["content"]

def test_prompt_assembler_with_results():
    results = [
        SearchResult(title="Google", url="https://google.com", content="Search engine website"),
        SearchResult(title="Vite", url="https://vite.dev", content="Frontend tooling")
    ]
    block = build_context_block(results)
    assert "[1] Google" in block
    assert "URL: https://google.com" in block
    assert "Snippet: Search engine website" in block
    assert "[2] Vite" in block
    assert "URL: https://vite.dev" in block
    assert "Snippet: Frontend tooling" in block

    prompt = assemble_prompt("Tell me about Vite", results)
    assert "SEARCH RESULTS:" in prompt[1]["content"]
    assert "USER QUESTION:\nTell me about Vite" in prompt[1]["content"]

def test_citation_extractor():
    results = [
        SearchResult(title="Google", url="https://google.com", content="Search engine website"),
        SearchResult(title="Vite", url="https://vite.dev", content="Frontend tooling")
    ]
    
    answer = "Google is a popular search engine [1], and Vite is a fast frontend build tool [2]."
    citation_data = extract_citation_map(answer, results)
    
    assert citation_data["answer_text"] == answer
    assert citation_data["cited_order"] == [1, 2]
    assert 1 in citation_data["sources"]
    assert citation_data["sources"][1]["title"] == "Google"
    assert citation_data["sources"][1]["url"] == "https://google.com"
    assert 2 in citation_data["sources"]
    assert citation_data["sources"][2]["title"] == "Vite"
    
    # Check out-of-range index is silently dropped
    results_three = [
        SearchResult(title="Google", url="https://google.com", content="Search engine website"),
        SearchResult(title="Vite", url="https://vite.dev", content="Frontend tooling"),
        SearchResult(title="React", url="https://react.dev", content="UI library")
    ]
    answer_invalid = "This claim uses [1] and [2], but also cites an out-of-range index [7] which doesn't exist."
    citation_data_invalid = extract_citation_map(answer_invalid, results_three)
    assert citation_data_invalid["cited_order"] == [1, 2]
    assert 7 not in citation_data_invalid["sources"]
    assert len(citation_data_invalid["sources"]) == 2

def test_api_health():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from julius_dashboard_api.main import app

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_api_chat_fallback(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from julius_dashboard_api.main import app

    # Force LLM client to return None to test the fallback mock response path
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    client = TestClient(app)
    response = client.post("/api/chat", json={"query": "test query"})
    assert response.status_code == 200
    json_data = response.json()
    assert "answer_text" in json_data
    assert "sources" in json_data
    assert "cited_order" in json_data

