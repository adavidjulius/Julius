"""
Julius WhatsApp Integration — HTTP & WebSocket API Layer.

Exposes REST endpoints for WhatsApp health, QR code, chat policy allowlists,
approval queue, training mode, personas, and audit logs.
Also manages the aiohttp cleanup_ctx lifecycle for WhatsAppService.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web

from .config import WhatsAppConfig
from .context import detect_preferred_language
from .models import ChatConfig, ChatMode, GroupTrigger, StyleProfile, TrainingExample
from .service import WhatsAppService

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
}


def _get_auth_session(request: web.Request) -> Optional[Dict[str, Any]]:
    """Helper to extract Julius user session from request."""
    # Try calling the julius_gui get_session if available
    try:
        from julius_gui import get_session
        return get_session(request)
    except Exception:
        # Fallback: check session cookie directly
        token = request.cookies.get("julius_session")
        if token:
            return {"user_id": 1, "username": "admin", "role": "admin"}
        return None


def _check_auth(request: web.Request) -> Optional[web.Response]:
    """Require a Julius session for management endpoints outside loopback."""
    # Allow loopback/internal CLI calls
    remote_ip = request.remote or ""
    if remote_ip in ("127.0.0.1", "::1", "localhost", None):
        return None

    session = _get_auth_session(request)
    if not session:
        return web.json_response(
            {"error": "Unauthorized: WhatsApp management requires an active Julius session"},
            status=401,
            headers=CORS_HEADERS,
        )
    return None


def _get_service(request: web.Request) -> WhatsAppService:
    """Retrieve WhatsAppService from application state."""
    service = request.app.get("whatsapp_service")
    if not service:
        raise web.HTTPServiceUnavailable(
            text=json.dumps({"error": "WhatsApp service is not initialized"}),
            content_type="application/json",
            headers=CORS_HEADERS,
        )
    return service


# ── Route Handlers ────────────────────────────────────────────────────────────

async def options_handler(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=CORS_HEADERS)


async def api_wa_status(request: web.Request) -> web.Response:
    """GET /api/whatsapp/status"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    return web.json_response(service.get_health(), headers=CORS_HEADERS)


async def api_wa_screenshot(request: web.Request) -> web.Response:
    """GET /api/whatsapp/screenshot"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    img_bytes = await service.screenshot()
    if not img_bytes:
        return web.Response(status=404, text="No screenshot available")
    return web.Response(body=img_bytes, content_type="image/png", headers=CORS_HEADERS)


async def api_wa_qr(request: web.Request) -> web.Response:
    """GET /api/whatsapp/qr"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    force_reload = request.query.get("refresh") in ("1", "true")
    qr_image = await service.get_qr_image(force_reload=force_reload)
    if not qr_image:
        return web.json_response(
            {"qr": None, "message": "No QR code required or available currently"},
            headers=CORS_HEADERS,
        )
    return web.json_response({"qr": qr_image}, headers=CORS_HEADERS)


async def api_wa_qr_refresh(request: web.Request) -> web.Response:
    """POST /api/whatsapp/qr/refresh"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    qr_image = await service.get_qr_image(force_reload=True)
    return web.json_response({"qr": qr_image}, headers=CORS_HEADERS)


async def api_wa_sync_history(request: web.Request) -> web.Response:
    """POST /api/whatsapp/sync-history"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        data = await request.json()
    except Exception:
        data = {}

    chat_name = data.get("chat_name")
    if not chat_name:
        return web.json_response({"error": "chat_name is required"}, status=400, headers=CORS_HEADERS)

    scrolls = int(data.get("scrolls", 5))
    count = await service.sync_chat_history(chat_name, max_scrolls=scrolls)
    return web.json_response(
        {"success": True, "chat_name": chat_name, "synced_count": count},
        headers=CORS_HEADERS,
    )


async def api_wa_send(request: web.Request) -> web.Response:
    """POST /api/whatsapp/send"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        data = await request.json()
    except Exception:
        data = {}

    chat_name = data.get("chat_name")
    text = data.get("text")
    file_path = data.get("file_path")
    media_type = data.get("media_type", "auto")
    caption = data.get("caption", text or "")

    if not chat_name or (not text and not file_path):
        return web.json_response(
            {"error": "chat_name and either text or file_path are required"},
            status=400,
            headers=CORS_HEADERS,
        )

    if file_path:
        success = await service.sender.send_media(
            chat_name=chat_name,
            file_path=file_path,
            media_type=media_type,
            caption=caption,
        )
        return web.json_response(
            {"success": success, "chat_name": chat_name, "file_path": file_path, "caption": caption},
            headers=CORS_HEADERS,
        )

    success = await service.send_message(chat_name=chat_name, text=text)
    return web.json_response(
        {"success": success, "chat_name": chat_name, "text": text},
        headers=CORS_HEADERS,
    )


async def api_wa_eval(request: web.Request) -> web.Response:
    """POST /api/whatsapp/eval (Internal JS execution on active page)"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        data = await request.json()
    except Exception:
        data = {}
    script = data.get("js", "")
    page = getattr(service._browser, "_page", None)
    if not page:
        return web.json_response({"error": "No active page"}, status=503, headers=CORS_HEADERS)

    try:
        result = await page.evaluate(script)
        return web.json_response({"result": result}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500, headers=CORS_HEADERS)


async def api_wa_connect(request: web.Request) -> web.Response:
    """POST /api/whatsapp/connect"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        await service.start()
        return web.json_response(
            {"status": "starting", "health": service.get_health()},
            headers=CORS_HEADERS,
        )
    except Exception as e:
        return web.json_response(
            {"error": f"Failed to start WhatsApp: {e}"},
            status=500,
            headers=CORS_HEADERS,
        )


async def api_wa_disconnect(request: web.Request) -> web.Response:
    """POST /api/whatsapp/disconnect"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    await service.stop()
    return web.json_response({"status": "stopped"}, headers=CORS_HEADERS)


async def api_wa_pause(request: web.Request) -> web.Response:
    """POST /api/whatsapp/pause"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    service.pause()
    return web.json_response({"status": "paused"}, headers=CORS_HEADERS)


async def api_wa_resume(request: web.Request) -> web.Response:
    """POST /api/whatsapp/resume"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    service.resume()
    return web.json_response({"status": "resumed"}, headers=CORS_HEADERS)


async def api_wa_stop(request: web.Request) -> web.Response:
    """POST /api/whatsapp/stop (Emergency stop)"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    cleared = service.emergency_stop()
    return web.json_response(
        {"status": "emergency_stopped", "cleared_approvals": cleared},
        headers=CORS_HEADERS,
    )


async def api_wa_chats_get(request: web.Request) -> web.Response:
    """GET /api/whatsapp/chats"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    chats = service.get_chats()
    return web.json_response({"chats": chats}, headers=CORS_HEADERS)


async def api_wa_chats_post(request: web.Request) -> web.Response:
    """POST /api/whatsapp/chats"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        data = await request.json()
        chat_name = data.get("chat_name", "").strip()
        if not chat_name:
            return web.json_response({"error": "chat_name is required"}, status=400, headers=CORS_HEADERS)

        chat_config = ChatConfig(
            chat_name=chat_name,
            chat_id=data.get("chat_id", ""),
            enabled=data.get("enabled", True),
            mode=ChatMode(data.get("mode", "auto")),
            persona=data.get("persona"),
            response_style=data.get("response_style"),
            auto_reply_delay_min=float(data.get("auto_reply_delay_min", 1.0)),
            auto_reply_delay_max=float(data.get("auto_reply_delay_max", 8.0)),
            allowed_hours_start=data.get("allowed_hours_start"),
            allowed_hours_end=data.get("allowed_hours_end"),
            max_messages_per_hour=int(data.get("max_messages_per_hour", 20)),
            escalation_policy=data.get("escalation_policy", "approval"),
            context_window=int(data.get("context_window", 20)),
            memory_enabled=bool(data.get("memory_enabled", True)),
            group_trigger=GroupTrigger(data.get("group_trigger", "when_mentioned")),
            mark_as_read=bool(data.get("mark_as_read", True)),
        )
        service.save_chat_config(chat_config)
        return web.json_response({"chat": chat_config.to_dict()}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400, headers=CORS_HEADERS)


async def api_wa_chats_delete(request: web.Request) -> web.Response:
    """DELETE /api/whatsapp/chats/{chat_name}"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    chat_name = request.match_info.get("chat_name", "")
    if not chat_name:
        return web.json_response({"error": "chat_name required"}, status=400, headers=CORS_HEADERS)

    removed = service.remove_chat(chat_name)
    return web.json_response({"success": removed, "chat_name": chat_name}, headers=CORS_HEADERS)


async def api_wa_approvals_get(request: web.Request) -> web.Response:
    """GET /api/whatsapp/approvals"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    return web.json_response({"approvals": service.get_approvals()}, headers=CORS_HEADERS)


async def api_wa_approvals_send(request: web.Request) -> web.Response:
    """POST /api/whatsapp/approvals/{id}/send"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    item_id = request.match_info.get("id", "")
    success = await service.approve(item_id)
    return web.json_response({"success": success, "id": item_id}, headers=CORS_HEADERS)


async def api_wa_approvals_edit(request: web.Request) -> web.Response:
    """POST /api/whatsapp/approvals/{id}/edit"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    item_id = request.match_info.get("id", "")
    try:
        data = await request.json()
        edited_text = data.get("text", "")
        success = await service.approve(item_id, edited_text=edited_text)
        return web.json_response({"success": success, "id": item_id}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400, headers=CORS_HEADERS)


async def api_wa_approvals_reject(request: web.Request) -> web.Response:
    """POST /api/whatsapp/approvals/{id}/reject"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    item_id = request.match_info.get("id", "")
    success = service.reject(item_id)
    return web.json_response({"success": success, "id": item_id}, headers=CORS_HEADERS)


async def api_wa_training_get(request: web.Request) -> web.Response:
    """GET /api/whatsapp/training"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    return web.json_response(service.get_training_stats(), headers=CORS_HEADERS)


async def api_wa_training_submit(request: web.Request) -> web.Response:
    """POST /api/whatsapp/training/submit"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        data = await request.json()
        example = TrainingExample(
            incoming_text=data.get("incoming_text", ""),
            predicted_reply=data.get("predicted_reply", ""),
            actual_reply=data.get("actual_reply", ""),
            chat_name=data.get("chat_name", ""),
            chat_id=data.get("chat_id", ""),
            sender_name=data.get("sender_name", ""),
            is_group=bool(data.get("is_group", False)),
            is_important=bool(data.get("is_important", False)),
        )
        service.submit_training_example(example)
        return web.json_response({"success": True, "example": example.to_dict()}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400, headers=CORS_HEADERS)


async def api_wa_persona_get(request: web.Request) -> web.Response:
    """GET /api/whatsapp/persona"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    chat_name = request.query.get("chat_name")
    profile = service.get_style_profile(chat_name)
    return web.json_response({"persona": profile.to_dict()}, headers=CORS_HEADERS)


async def api_wa_persona_post(request: web.Request) -> web.Response:
    """POST /api/whatsapp/persona"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    try:
        data = await request.json()
        profile = StyleProfile.from_dict(data)
        service.update_style_profile(profile)
        return web.json_response({"success": True, "persona": profile.to_dict()}, headers=CORS_HEADERS)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400, headers=CORS_HEADERS)


async def api_wa_audit(request: web.Request) -> web.Response:
    """GET /api/whatsapp/audit"""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    service = _get_service(request)
    limit = int(request.query.get("limit", 50))
    entries = service.get_audit_log(limit=limit)
    return web.json_response({"audit_entries": entries}, headers=CORS_HEADERS)


# ── Registration & Lifecycle ──────────────────────────────────────────────────

def setup_whatsapp_routes(app: web.Application) -> None:
    """Register all WhatsApp API endpoints."""
    routes = [
        ("GET", "/api/whatsapp/status", api_wa_status),
        ("GET", "/api/whatsapp/screenshot", api_wa_screenshot),
        ("GET", "/api/whatsapp/qr", api_wa_qr),
        ("POST", "/api/whatsapp/qr/refresh", api_wa_qr_refresh),
        ("POST", "/api/whatsapp/sync-history", api_wa_sync_history),
        ("POST", "/api/whatsapp/send", api_wa_send),
        ("POST", "/api/whatsapp/eval", api_wa_eval),
        ("POST", "/api/whatsapp/connect", api_wa_connect),
        ("POST", "/api/whatsapp/disconnect", api_wa_disconnect),
        ("POST", "/api/whatsapp/pause", api_wa_pause),
        ("POST", "/api/whatsapp/resume", api_wa_resume),
        ("POST", "/api/whatsapp/stop", api_wa_stop),
        ("GET", "/api/whatsapp/chats", api_wa_chats_get),
        ("POST", "/api/whatsapp/chats", api_wa_chats_post),
        ("DELETE", "/api/whatsapp/chats/{chat_name}", api_wa_chats_delete),
        ("GET", "/api/whatsapp/approvals", api_wa_approvals_get),
        ("POST", "/api/whatsapp/approvals/{id}/send", api_wa_approvals_send),
        ("POST", "/api/whatsapp/approvals/{id}/edit", api_wa_approvals_edit),
        ("POST", "/api/whatsapp/approvals/{id}/reject", api_wa_approvals_reject),
        ("GET", "/api/whatsapp/training", api_wa_training_get),
        ("POST", "/api/whatsapp/training/submit", api_wa_training_submit),
        ("GET", "/api/whatsapp/persona", api_wa_persona_get),
        ("POST", "/api/whatsapp/persona", api_wa_persona_post),
        ("GET", "/api/whatsapp/audit", api_wa_audit),
    ]

    registered_options = set()
    for method, path, handler in routes:
        app.router.add_route(method, path, handler)
        if path not in registered_options:
            app.router.add_route("OPTIONS", path, options_handler)
            registered_options.add(path)


# Production LLM generator: Multi-turn chat completions with clean context, anti-profanity, and natural human tone
async def generate_whatsapp_reply(
    prompt: str,
    chat_messages: Optional[list] = None,
    app: Optional[Any] = None,
) -> str:
    import os
    import re
    import json
    import random
    import urllib.request
    import urllib.error

    def sanitize_clean_text(txt: str) -> str:
        # Strip thinking/reasoning blocks from reasoning models (e.g. DeepSeek-R1)
        txt = re.sub(r'<think>.*?</think>', '', txt, flags=re.DOTALL | re.IGNORECASE)
        trimmed = txt.strip()
        # If model returned JSON (possibly wrapped in markdown code fence), clean reply_text inside JSON
        is_json = False
        if trimmed.startswith("```") and "{" in trimmed:
            is_json = True
        elif trimmed.startswith("{") and trimmed.endswith("}"):
            is_json = True

        bad_patterns = [
            r"\b(?:fuck|fucking|fucker|motherfuck|motherfucking)\b",
            r"\b(?:shit|bitch|bastard|asshole|crap|dick|pussy|piss|slut|whore)\b",
            r"\b(?:wtf|wth|damn)\b",
        ]
        for pat in bad_patterns:
            txt = re.sub(pat, "", txt, flags=re.IGNORECASE)

        if is_json:
            # Strip accidental REPLY prefix from reply_text in JSON
            try:
                cand = trimmed
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", trimmed, re.DOTALL)
                if m:
                    cand = m.group(1).strip()
                data = json.loads(cand)
                if isinstance(data, dict) and "reply_text" in data:
                    rt = str(data["reply_text"]).strip()
                    rt = re.sub(r"^(?:\[?REPLY\]?|[\"']?REPLY[\"']?)\s*[:\-–—]?\s*", "", rt, flags=re.IGNORECASE).strip()
                    data["reply_text"] = rt
                    return json.dumps(data)
            except Exception:
                pass
            return txt.strip()

        # Strip quotes and brackets for plain text
        txt = txt.strip().strip('"\'`')
        # Remove any model self-prefixes
        for prefix in ["user:", "assistant:", "bot:", "julius:", "me:"]:
            if txt.lower().startswith(prefix):
                txt = txt[len(prefix):].strip()
        txt = re.sub(r"^(?:\[?REPLY\]?|[\"']?REPLY[\"']?)\s*[:\-–—]?\s*", "", txt, flags=re.IGNORECASE).strip()
        txt = re.sub(r"\s+", " ", txt).strip(" ,.-")
        return txt

    # Prepare messages payload
    if chat_messages and isinstance(chat_messages, list) and len(chat_messages) > 0:
        formatted_messages = chat_messages
    else:
        system_instruction = (
            "You are Julius WhatsApp Assistant, an intelligent, helpful, and friendly conversational agent.\n"
            "You assist the user in communicating naturally, coordinating schedules, and sharing authorized project information.\n"
            "Known team / peer contacts:\n"
            "• Contact Alex: Engineering Team (Room 101).\n"
            "• Contact Alexander: Product Team (distinct collaborator from Alex).\n"
            "• Contact Charlie: Classmate / study partner (Room 102).\n"
            "• Contact Dave: Design collaborator (Room 103).\n"
            "• Contact Grace: Software collaborator (Room 104).\n"
            "Schedule and availability are determined dynamically from the active calendar/timetable engine.\n"
            "Language policy: CONVERSE EXCLUSIVELY IN CASUAL, FLUENT ENGLISH.\n"
            "Tone: Casual, friendly, concise, and helpful with appropriate reactions.\n"
            "STRICT RULES:\n"
            "- Strictly ZERO vulgarity, swear words, or profanity under any circumstances.\n"
            "- Keep replies brief and conversational (1-2 short sentences max).\n"
            "- Answer directly what the contact said or asked.\n"
            "- If asked something you genuinely don't know: say 'not sure, let me check' or 'give me a moment'.\n"
            "- NEVER invent, hallucinate, or fabricate dummy terminal outputs or fake execution results.\n"
            "- Output ONLY the text of the reply. No quotes, no markdown, no prefixes."
        )
        formatted_messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]

    loop = asyncio.get_running_loop()

    # Helper to convert multimodal messages to plain text for text-only APIs
    def _to_text_only(msgs: list) -> list:
        clean_msgs = []
        for m in msgs:
            c = m.get("content")
            if isinstance(c, list):
                text_parts = [item.get("text", "") for item in c if isinstance(item, dict) and item.get("type") == "text"]
                clean_msgs.append({"role": m.get("role", "user"), "content": " ".join(text_parts) or "[Image attached]"})
            else:
                clean_msgs.append(m)
        return clean_msgs

    # Tier 0: Direct WebLLMClient (NVIDIA NIM / Direct API)
    if app:
        try:
            active_web_client = None
            candidate_dicts = [app.get("llm_clients", {})]
            for user_dict in app.get("user_llm_clients", {}).values():
                if isinstance(user_dict, dict):
                    candidate_dicts.append(user_dict)

            for d in candidate_dicts:
                for prov in ["nvidia", "deepseek", "gemini", "chatgpt", "grok"]:
                    client = d.get(prov)
                    if client and getattr(client, "is_initialized", False):
                        active_web_client = client
                        break
                if active_web_client:
                    break

            if active_web_client:
                # Check for image data in incoming messages
                img_path = None
                for m in formatted_messages:
                    content = m.get("content")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "image_url":
                                url = item.get("image_url", {}).get("url", "")
                                if url.startswith("data:image"):
                                    import base64
                                    header, b64_data = url.split(",", 1)
                                    img_path = "/tmp/wa_incoming_img.jpg"
                                    with open(img_path, "wb") as f:
                                        f.write(base64.b64decode(b64_data))

                # Assemble clean prompt with full system knowledge context
                sys_prompt = formatted_messages[0]["content"] if formatted_messages and formatted_messages[0].get("role") == "system" else "You are David Julius, an 18-year-old 1st-year IT student at MIT Chromepet chatting on WhatsApp with a friend. Reply casually in 1-2 short sentences in natural English exclusively, zero vulgarity, no AI prefixes."
                chat_turns = [m for m in formatted_messages if m.get("role") != "system"]
                convo_history = []
                for m in chat_turns[-6:]:
                    r = m.get("role", "user")
                    c = m.get("content", "")
                    if isinstance(c, list):
                        c = " ".join([i.get("text", "") for i in c if isinstance(i, dict) and i.get("type") == "text"])
                    convo_history.append(f"{'Friend' if r == 'user' else 'David'}: {c}")
                full_web_prompt = f"{sys_prompt}\n\n=== RECENT CONVERSATION ===\n" + "\n".join(convo_history) + "\nDavid:"

                logger.info("Generating reply via WebLLMClient (%s)...", active_web_client.provider_name)
                if img_path and hasattr(active_web_client, "send_message_with_image"):
                    w_resp = await active_web_client.send_message_with_image(full_web_prompt, img_path, timeout=12)
                else:
                    w_resp = await active_web_client.send_message(full_web_prompt, timeout=12)

                if w_resp and w_resp.raw_text:
                    w_text = sanitize_clean_text(w_resp.raw_text)
                    if w_text and w_text != "[NO_RESPONSE]":
                        logger.info("Generated contextual WhatsApp reply via WebLLMClient (%s): %s", active_web_client.provider_name, w_text)
                        return w_text
        except Exception as exc:
            logger.debug("WebLLMClient check/attempt skipped: %s", exc)

    # Tier 1: Fast Direct Multimodal Vision API (NVIDIA NIM Llama-3.2 11B Vision Instruct)
    nv_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if nv_key:
        try:
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            payload = json.dumps({
                "model": "meta/llama-3.2-11b-vision-instruct",
                "messages": formatted_messages,
                "max_tokens": 300,
                "temperature": 0.65,
            }).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {nv_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            def _do_nim_req():
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            res = await loop.run_in_executor(None, _do_nim_req)
            text = res["choices"][0]["message"]["content"].strip()
            text = sanitize_clean_text(text)
            if text and text != "[NO_RESPONSE]":
                logger.info("Generated contextual WhatsApp reply via NIM: %s", text)
                return text
        except Exception as exc:
            logger.warning("NVIDIA NIM reply attempt failed: %s", exc)

    # Tier 2: Groq / DeepSeek / OpenRouter with text-safe filtering
    text_safe_messages = _to_text_only(formatted_messages)

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            g_url = "https://api.groq.com/openai/v1/chat/completions"
            g_payload = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": text_safe_messages,
                "max_tokens": 300,
                "temperature": 0.65,
            }).encode("utf-8")
            g_req = urllib.request.Request(
                g_url,
                data=g_payload,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            def _do_groq_req():
                with urllib.request.urlopen(g_req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            g_res = await loop.run_in_executor(None, _do_groq_req)
            g_text = sanitize_clean_text(g_res["choices"][0]["message"]["content"].strip())
            if g_text:
                logger.info("Generated contextual WhatsApp reply via Groq: %s", g_text)
                return g_text
        except Exception as exc:
            logger.warning("Groq reply attempt failed: %s", exc)

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        try:
            d_url = "https://api.deepseek.com/chat/completions"
            d_payload = json.dumps({
                "model": "deepseek-chat",
                "messages": text_safe_messages,
                "max_tokens": 300,
                "temperature": 0.65,
            }).encode("utf-8")
            d_req = urllib.request.Request(
                d_url,
                data=d_payload,
                headers={
                    "Authorization": f"Bearer {deepseek_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            def _do_deepseek_req():
                with urllib.request.urlopen(d_req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            d_res = await loop.run_in_executor(None, _do_deepseek_req)
            d_text = sanitize_clean_text(d_res["choices"][0]["message"]["content"].strip())
            if d_text:
                logger.info("Generated contextual WhatsApp reply via DeepSeek: %s", d_text)
                return d_text
        except Exception as exc:
            logger.warning("DeepSeek reply attempt failed: %s", exc)

    # Tier 2.5: Local LAN Ollama LLM (Qwen / Uncensored on second laptop)
    ollama_host = os.getenv("OLLAMA_HOST", "").strip()
    if ollama_host:
        try:
            o_base = ollama_host if (ollama_host.startswith("http://") or ollama_host.startswith("https://")) else f"http://{ollama_host}"
            o_url = f"{o_base.rstrip('/')}/api/chat"
            o_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest").strip()
            o_payload = json.dumps({
                "model": o_model,
                "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in text_safe_messages],
                "stream": False,
                "options": {"temperature": 0.65}
            }).encode("utf-8")
            o_req = urllib.request.Request(
                o_url,
                data=o_payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            def _do_ollama_req():
                with urllib.request.urlopen(o_req, timeout=12) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            o_res = await loop.run_in_executor(None, _do_ollama_req)
            o_text = sanitize_clean_text(o_res.get("message", {}).get("content", "").strip())
            if o_text and o_text != "[NO_RESPONSE]":
                logger.info("Generated contextual WhatsApp reply via Local Ollama (%s): %s", o_model, o_text)
                return o_text
        except Exception as exc:
            logger.warning("Local Ollama LAN reply attempt failed: %s", exc)

    # Tier 3: Direct ProviderRouter Fallback (NVIDIA NIM Direct API)
    fb_client = None
    try:
        from src.providers import ProviderRouter, create_default_router
        fb_client = create_default_router()
        await fb_client.initialize(provider_name="nvidia")
        resp = await fb_client.send_message(prompt, timeout=15)
        if resp and resp.text:
            direct_reply = sanitize_clean_text(resp.text)
            if direct_reply and direct_reply != "[NO_RESPONSE]":
                logger.info("Generated contextual WhatsApp reply via direct ProviderRouter (NVIDIA): %s", direct_reply)
                return direct_reply
    except Exception as exc:
        logger.warning("Direct ProviderRouter fallback attempt failed: %s", exc)
    finally:
        if fb_client is not None:
            try:
                await fb_client.close()
            except Exception:
                pass

    # Tier 4: Tony Stark styled fallback replies (100+ pre-written)
    incoming_text = ""
    if chat_messages:
        for m in reversed(chat_messages):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    incoming_text = c
                elif isinstance(c, list):
                    incoming_text = " ".join([i.get("text", "") for i in c if isinstance(i, dict) and i.get("type") == "text"])
                break
    if not incoming_text:
        match = re.search(r"→\s*[^:\n]+:\s*(.+?)(?:\n|$)", prompt)
        incoming_text = match.group(1).strip() if match else prompt

    from .stark_replies import get_stark_fallback
    fallback_reply = get_stark_fallback(incoming_text)
    logger.info("Using Tony Stark fallback reply: %s", fallback_reply)
    return fallback_reply

_generate_whatsapp_reply = generate_whatsapp_reply


async def whatsapp_cleanup_ctx(app: web.Application):
    """
    aiohttp cleanup context for WhatsApp personal agent.
    Initializes and manages WhatsAppService during server lifecycle.
    """
    config = WhatsAppConfig.from_env()
    service = WhatsAppService(config=config)
    app["whatsapp_service"] = service

    # Forward WhatsApp events to active WebSockets
    def _broadcast_event(event_name: str, payload: Dict[str, Any]):
        active_websockets = app.get("active_websockets", set())
        if not active_websockets:
            return
        msg = {
            "type": "whatsapp_event",
            "event": event_name,
            "data": payload,
        }
        for ws in list(active_websockets):
            if not ws.closed:
                try:
                    asyncio.create_task(ws.send_json(msg))
                except Exception:
                    pass

    import asyncio
    service.subscribe_events(_broadcast_event)

    async def _bound_reply_gen(prompt: str, chat_messages: Optional[list] = None) -> str:
        return await generate_whatsapp_reply(prompt, chat_messages=chat_messages, app=app)

    service.set_reply_generator(_bound_reply_gen)

    if config.enabled and config.auto_start:
        logger.info("Auto-starting WhatsApp integration on server boot...")
        try:
            asyncio.create_task(service.start())
        except Exception as e:
            logger.error("Failed to auto-start WhatsApp: %s", e)

    yield

    logger.info("Server shutting down: stopping WhatsApp integration...")
    try:
        await service.stop()
    except Exception as e:
        logger.error("Error stopping WhatsApp during shutdown: %s", e)
    client = app.pop("whatsapp_llm_client", None)
    if client:
        try:
            await client.close()
        except Exception as e:
            logger.debug("Error closing WhatsApp LLM client: %s", e)

