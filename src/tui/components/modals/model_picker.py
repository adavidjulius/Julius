"""
Neural model picker modal (F2 or /model).
"""

from __future__ import annotations

from typing import List, Tuple, Optional
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option


MODELS: List[Tuple[str, str, str]] = [
    ("nvidia", "NVIDIA Nemotron 550B (Build Free API)", "NVIDIA NIM Free API · 550B Ultra Reasoning & Code"),
    ("aifreeforever", "DeepSeek-V4 Flash (Free Forever)", "Free fast multi-model web - AIFreeForever"),
    ("deepseek", "DeepSeek-R1", "Deep multi-stage reasoning & architecture"),
    ("chatgpt", "ChatGPT o3-mini", "High-accuracy code generation & synthesis"),
    ("grok", "Grok-3", "Fast real-time logic and shell operations"),
    ("gemini", "Gemini 2.0 Flash", "Multimodal perception & long-context"),
    ("kimi", "Moonshot Kimi K3", "Long-context reasoning & math specialist"),
    ("perplexity", "Perplexity Sonar", "Live web search & grounded citations"),
    ("ollama", "Local Ollama LLM", "Private LAN uncensored neural model with DeepSeek fallback"),
]


class ModelPickerModal(ModalScreen[Optional[str]]):
    """Calm model switcher overlay sheet."""

    DEFAULT_CSS = """
    ModelPickerModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #model-card {
        width: 78;
        max-width: 92%;
        height: auto;
        max-height: 85%;
        background: #18181b;
        border: round #c8b896;
        padding: 1 2;
        layout: vertical;
    }

    #model-title {
        color: #f5f5f7;
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 0;
    }

    #model-subtitle {
        color: #c8b896;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    #model-options {
        width: 100%;
        height: auto;
        max-height: 12;
        background: #0d0d0f;
        border: round #3e3e42;
        padding: 0 1;
        margin-bottom: 1;
        scrollbar-size: 0 0;
    }

    #model-options:hover {
        scrollbar-size-vertical: 1;
    }

    #model-options > .option-list--option-highlighted {
        background: #2c2c2e;
        color: #f5f5f7;
        text-style: bold;
    }

    #model-footer {
        color: #86868b;
        text-align: center;
        width: 100%;
    }
    """

    def __init__(self, current_model: str = "deepseek", **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_model = current_model.lower()

    def compose(self) -> ComposeResult:
        with Vertical(id="model-card"):
            yield Label("Select Reasoning Model", id="model-title")
            yield Label("Choose active neural provider for reasoning & tool execution", id="model-subtitle")
            yield OptionList(id="model-options")
            yield Label("[Enter] Select    [Esc] Dismiss", id="model-footer")

    async def on_mount(self) -> None:
        opt_list = self.query_one("#model-options", OptionList)
        opt_list.clear_options()

        # Probe live Ollama models on LAN
        live_ollama: List[Tuple[str, str, str]] = []
        try:
            import aiohttp
            import os
            base_url = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
            timeout_obj = aiohttp.ClientTimeout(total=0.8)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(f"{base_url}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for m in data.get("models", []):
                            raw_name = m.get("name", "")
                            if not raw_name:
                                continue
                            lower_name = raw_name.lower()
                            if "lexi" in lower_name:
                                live_ollama.append(("lexi", "Llama 3.1 8B Lexi", "Local LAN (Ollama 8.0B)"))
                            elif "qwen" in lower_name:
                                live_ollama.append(("qwen", "Qwen 3.5 9B", "Local LAN (Ollama 8.95B)"))
                            elif "70b" in lower_name:
                                live_ollama.append(("llama70b", "Llama 3 70B", "Local LAN (Ollama 70B)"))
                            else:
                                clean = raw_name.split("/")[-1].split(":")[0]
                                live_ollama.append((clean.lower(), clean, "Local LAN (Ollama)"))
        except Exception:
            pass

        # Build dynamic model list
        display_models = []
        if live_ollama:
            display_models.extend(live_ollama)
        for m_id, name, desc in MODELS:
            if m_id == "ollama" and live_ollama:
                continue
            display_models.append((m_id, name, desc))

        for idx, (model_id, name, desc) in enumerate(display_models):
            is_active = (model_id == self.current_model or (self.current_model == "ollama" and idx == 0))
            prefix = "✓ " if is_active else "  "
            line = f"{prefix}{name:<18} · {desc}"
            opt_list.add_option(Option(line, id=model_id))
            if is_active:
                opt_list.highlighted = idx

        opt_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
