# prompt_assembler.py
from .search_connector import SearchResult

SYSTEM_INSTRUCTIONS = """You are a research assistant. You have been given a set of \
numbered search snippets retrieved from the live web. Follow these rules exactly:

1. Base your answer ONLY on the information in the snippets below. Do not use prior \
knowledge unless the snippets are insufficient — in that case, say so explicitly.
2. Every factual claim must include an inline citation in the format [n], where n \
matches the snippet number it came from.
3. If snippets conflict, note the disagreement and cite both sources.
4. If none of the snippets answer the question, say so plainly instead of guessing.
5. Do not fabricate snippet numbers or URLs that were not provided.
"""


def build_context_block(results: list[SearchResult]) -> str:
    if not results:
        return "No search results were available for this query."

    lines = []
    for i, r in enumerate(results, start=1):
        lines.append(f"[{i}] {r.title}\nURL: {r.url}\nSnippet: {r.content}\n")
    return "\n".join(lines)


def assemble_prompt(user_query: str, results: list[SearchResult]) -> list[dict]:
    """
    Returns a chat-style message list ready to send to the LLM endpoint.
    Kept as an abstract 'messages' array so it plugs into any
    OpenAI-style /completions or local inference endpoint.
    """
    context_block = build_context_block(results)

    user_content = (
        f"SEARCH RESULTS:\n{context_block}\n\n"
        f"USER QUESTION:\n{user_query}\n\n"
        f"Answer the question using the rules above, citing sources as [n]."
    )

    return [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_content},
    ]
