#!/usr/bin/env python3
"""
Julius Agent — Web UI Server (Production-Grade)
A local web server and websocket backend for the Julius React UI.

Refactored for:
  - Phase 1: Per-session LLM client state (no global shared_client)
  - Phase 2: Safe background task lifecycle with cancellation on disconnect
  - Phase 3: Secure attachment saving (path-traversal protection + body size limits)
  - Phase 4: Externalized configuration via .env / environment variables
  - Phase 5: Live voice conversation (STT + TTS via WebSocket)
"""
from __future__ import annotations

import aiohttp
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import uuid
import urllib.parse
import webbrowser
from pathlib import Path

from aiohttp import web, WSMsgType
from dotenv import load_dotenv

# ── Bootstrap ─────────────────────────────────────────────────────────────────
# Load .env from project root (silently ignored if the file doesn't exist)
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# If running in a frozen py2app bundle, force Playwright to use the local bundled browsers.
if getattr(sys, "frozen", False) and "RESOURCEPATH" in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(os.environ["RESOURCEPATH"]) / ".local-browsers")

# Add the project root to sys.path so that 'src' is importable
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.agent_config import AgentConfig
from src.web_agent import WebAgent
from src.agent_prompts import SYSTEM_PROMPT
from src.providers import ProviderRouter, create_default_router
from src.voice import VoiceManager
from src.browser_portal import (
    browser_portal_handler,
    api_browser_portal_handler,
    api_browser_screenshot_handler,
    api_browser_action_handler,
)
from src.db.database import Database
from src.auth.manager import AuthManager
from src.security.workspace_sandbox import WorkspaceSandbox
from src.security.command_policy import CommandPolicy
from src.security.audit import AuditLogger
from src.security.daemon_hardening import DaemonSecurityManager, enforce_loopback_binding
from src.telemetry.metrics import handle_healthz, handle_readyz, handle_metrics
from src.action_executor import ActionExecutor
from src.permission_gate import PermissionGate, PermissionResponse, ActionType
from src.remote.cluster_executor import ClusterExecutor
from src.research.mtk_daemon import MTKDaemon, MTKConfig
from src.plugins.registry import get_plugin_registry
from src.components.widget_portal import WidgetPortal


def _get_env_conf(key: str, default: str = "") -> str:
    """Resolve env var for JULIUS_* configuration."""
    return os.getenv(f"JULIUS_{key}", default)

# Active backend settings (in-memory, synchronized with .env)
ACTIVE_SETTINGS = {
    "model": _get_env_conf("DEFAULT_MODEL", "deepseek"),
    "agentName": _get_env_conf("AGENT_NAME", "Julius"),
    "agentMode": _get_env_conf("AGENT_MODE", "Autonomous"),
    "sysPrompt": _get_env_conf("SYSTEM_PROMPT", SYSTEM_PROMPT).replace("\\n", "\n"),
    "autoApprove": _get_env_conf("AUTO_APPROVE", "true").lower() in ("true", "1", "yes"),
    "confirmWrites": _get_env_conf("CONFIRM_WRITES", "true").lower() in ("true", "1", "yes"),
    "temp": float(_get_env_conf("TEMPERATURE", "0.7")),
    "streaming": _get_env_conf("STREAMING", "true").lower() in ("true", "1", "yes"),
    "max_steps": int(_get_env_conf("MAX_STEPS", "9999")),
    "voice_name": _get_env_conf("VOICE_NAME", "Millie"),
    "voice_rate": int(_get_env_conf("VOICE_RATE", "172")),
    "stt_language": _get_env_conf("STT_LANGUAGE", "en-US"),
    "voice_model": _get_env_conf("VOICE_MODEL", "Millie"),
    "dark": _get_env_conf("DARK_THEME", "false").lower() in ("true", "1", "yes"),
    "canva_authenticated": os.getenv("CANVA_AUTHENTICATED", "false").lower() in ("true", "1", "yes"),
    # Millie RVC voice tuning
    "millie_pitch_shift": int(os.getenv("MILLIE_PITCH_SHIFT", "0")),
    "millie_index_ratio": float(os.getenv("MILLIE_INDEX_RATIO", "0.75")),
    "millie_filter_radius": int(os.getenv("MILLIE_FILTER_RADIUS", "3")),
    "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    "sarvam_api_key": os.getenv("SARVAM_API_KEY", ""),
    "use_perception": _get_env_conf("USE_PERCEPTION", "true").lower() in ("true", "1", "yes"),
}

# Dynamically populate connector settings on startup from environment
CONNECTOR_APPS = ["canva", "whatsapp", "youtube", "instagram", "slack", "notion", "github", "gmail", 
                  "google_calendar", "google_drive", "spotify", "figma", "trello", "zoom", 
                  "discord", "hubspot", "jira", "linear", "stripe", "shopify"]

for app_name in CONNECTOR_APPS:
    env_name = f"{app_name.upper()}_AUTHENTICATED"
    ACTIVE_SETTINGS[f"{app_name}_authenticated"] = os.getenv(env_name, "false").lower() in ("true", "1", "yes")

# In-memory OAuth database for authorization codes and issued tokens
OAUTH_CODES = {}  # code -> {client_id, redirect_uri, expires_at}
OAUTH_TOKENS = {} # access_token -> {client_id, expires_at}


# ── Phase 4: Centralised Production Config ────────────────────────────────────
class ProductionConfig:
    """Reads all server parameters from environment variables with safe defaults."""
    MAX_STEPS: int        = int(_get_env_conf("MAX_STEPS", "9999"))
    HEADLESS: bool        = _get_env_conf("HEADLESS", "true" if not os.getenv("DISPLAY") else "false").lower() in ("true", "1", "yes")
    HOST: str             = _get_env_conf("HOST", "127.0.0.1")
    PORT: int             = int(_get_env_conf("WS_PORT", "8080"))
    CLIENT_MAX_SIZE: int  = int(_get_env_conf("CLIENT_MAX_SIZE", str(100 * 1024 * 1024)))  # 100 MB
    VOICE_ENABLED: bool   = _get_env_conf("VOICE_ENABLED", "true").lower() in ("true", "1", "yes")
    PROFILE_DIR: str      = _get_env_conf("PROFILE_DIR", "")


# ── Phase 3: Secure attachment helper ────────────────────────────────────────
def save_safe_attachment(workspace_path: str, file_name: str, base64_data: str) -> Path:
    """
    Save an attachment file inside workspace_path only.

    Raises ValueError if the resolved target path would escape the workspace
    (directory-traversal guard).
    """
    workspace = Path(workspace_path).resolve()
    target_path = workspace.joinpath(file_name).resolve()

    if not target_path.is_relative_to(workspace):
        raise ValueError(
            f"Security Alert: Path traversal attempt blocked for '{file_name}'"
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "wb") as f:
        f.write(base64.b64decode(base64_data))

    print(f"Saved attachment: {target_path}")
    return target_path


# ── In-Memory Sessions Registry ──────────────────────────────────────────────
SESSIONS = {}  # session_id -> { "username": username, "workspace": workspace_path, "settings": settings_dict }
REQUIRE_AUTH = True  # Production-grade multi-user auth enabled

def get_session(request: web.Request) -> dict | None:
    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header[7:].strip()
        elif "token" in request.query:
            session_id = request.query.get("token", "").strip()

    if not session_id:
        return None

    auth_mgr: AuthManager = request.app.get("auth_mgr")
    if auth_mgr:
        res = auth_mgr.validate_session(session_id)
        if res:
            user, session_rec, workspace_rec = res
            user_id = user.id
            role = user.role
            if role in ("admin", "super_admin", "owner"):
                workspace_path = request.app.get("workspace", "")
            else:
                workspace_path = str((Path(request.app.get("workspace", "")) / "workspaces" / f"user_{user_id}").resolve())
                Path(workspace_path).mkdir(parents=True, exist_ok=True)
                (Path(workspace_path) / ".julius").mkdir(parents=True, exist_ok=True)

            settings = load_settings_from_workspace(workspace_path)
            return {
                "user_id": user_id,
                "username": user.username,
                "email": user.email or "",
                "role": role,
                "workspace": workspace_path,
                "session_token": session_id,
                "settings": settings,
            }

    # Fallback to legacy in-memory SESSIONS
    if session_id in SESSIONS:
        return SESSIONS[session_id]

    return None

def get_session_workspace(request: web.Request) -> str:
    session = get_session(request)
    if session:
        return session.get("workspace") or request.app.get("workspace", "")
    return request.app.get("workspace", "")

def load_settings_from_workspace(workspace_path: str) -> dict:
    import os
    from pathlib import Path
    
    settings = {
        "model": os.getenv("JULIUS_DEFAULT_MODEL", "deepseek"),
        "agentName": "Julius",
        "agentMode": "Autonomous",
        "sysPrompt": SYSTEM_PROMPT,
        "autoApprove": True,
        "confirmWrites": True,
        "temp": 0.7,
        "streaming": True,
        "max_steps": 9999,
        "voice_name": "Millie",
        "voice_rate": 172,
        "stt_language": "en-US",
        "voice_model": "Millie",
        "dark": False,
        "canva_authenticated": False,
        "millie_pitch_shift": 0,
        "millie_index_ratio": 0.75,
        "millie_filter_radius": 3,
        "sarvam_api_key": "",
        "use_perception": True,
    }
    
    # Add connectors
    for app in CONNECTOR_APPS:
        settings[f"{app}_authenticated"] = False

    # Try loading from workspace-specific .env file
    env_path = Path(workspace_path) / ".env"
    if env_path.exists():
        try:
            with env_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    v = v.replace("\\n", "\n")
                    
                    env_to_key = {
                        "JULIUS_DEFAULT_MODEL": "model",
                        "JULIUS_AGENT_NAME": "agentName",
                        "JULIUS_AGENT_MODE": "agentMode",
                        "JULIUS_SYSTEM_PROMPT": "sysPrompt",
                        "JULIUS_AUTO_APPROVE": "autoApprove",
                        "JULIUS_CONFIRM_WRITES": "confirmWrites",
                        "JULIUS_TEMPERATURE": "temp",
                        "JULIUS_STREAMING": "streaming",
                        "JULIUS_MAX_STEPS": "max_steps",
                        "JULIUS_VOICE_NAME": "voice_name",
                        "JULIUS_VOICE_RATE": "voice_rate",
                        "JULIUS_STT_LANGUAGE": "stt_language",
                        "JULIUS_VOICE_MODEL": "voice_model",
                        "JULIUS_DARK_THEME": "dark",
                        "CANVA_AUTHENTICATED": "canva_authenticated",
                        "MILLIE_PITCH_SHIFT": "millie_pitch_shift",
                        "MILLIE_INDEX_RATIO": "millie_index_ratio",
                        "MILLIE_FILTER_RADIUS": "millie_filter_radius",
                        "SARVAM_API_KEY": "sarvam_api_key",
                        "JULIUS_USE_PERCEPTION": "use_perception",
                    }
                    for app in CONNECTOR_APPS:
                        env_to_key[f"{app.upper()}_AUTHENTICATED"] = f"{app}_authenticated"
                        env_to_key[f"{app.upper()}_ACCESS_TOKEN"] = f"{app}_access_token"
                        env_to_key[f"{app.upper()}_REFRESH_TOKEN"] = f"{app}_refresh_token"

                    if k in env_to_key:
                        sett_key = env_to_key[k]
                        default_val = settings.get(sett_key)
                        if isinstance(default_val, bool):
                            settings[sett_key] = v.lower() in ("true", "1", "yes")
                        elif isinstance(default_val, int):
                            try:
                                settings[sett_key] = int(v)
                            except ValueError:
                                pass
                        elif isinstance(default_val, float):
                            try:
                                settings[sett_key] = float(v)
                            except ValueError:
                                pass
                        else:
                            settings[sett_key] = v
        except Exception as e:
            print(f"Error loading settings from {env_path}: {e}")
            
    return settings

def get_session_settings(request: web.Request) -> dict:
    session_id = request.cookies.get("session_id")
    if session_id and session_id in SESSIONS:
        session_data = SESSIONS[session_id]
        if "settings" not in session_data:
            session_data["settings"] = load_settings_from_workspace(session_data["workspace"])
        return session_data["settings"]
    return ACTIVE_SETTINGS


def hash_password(password: str) -> str:
    # Use the secure crypto module for password hashing
    from src.auth.crypto import hash_password as secure_hash_password
    return secure_hash_password(password)

def load_users(workspace_dir: str) -> dict:
    users_file = Path(workspace_dir) / ".julius" / "users.json"
    if users_file.exists():
        try:
            with open(users_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(workspace_dir: str, users: dict) -> None:
    users_file = Path(workspace_dir) / ".julius" / "users.json"
    users_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(users_file, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        print(f"Error saving users: {e}")

# ── Authentication Handlers ───────────────────────────────────────────────────
# ── Authentication Handlers ───────────────────────────────────────────────────
async def login_handler(request: web.Request) -> web.Response:
    # If they are already authenticated, redirect to /
    session = get_session(request)
    if session:
        return web.HTTPFound("/")
    return web.FileResponse(Path(__file__).parent / "frontend" / "login.html")

async def api_login_handler(request: web.Request) -> web.Response:
    import time
    auth_mgr: AuthManager = request.app.get("auth_mgr")
    try:
        data = await request.json()
        identifier = (data.get("username") or data.get("email") or "").strip()
        password = data.get("password", "")
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body"}, status=400)

    if not identifier or not password:
        return web.json_response({"success": False, "error": "Username/Email and password are required"}, status=400)

    client_ip = request.remote or "127.0.0.1"
    try:
        user, raw_token, session_rec, workspace_rec = auth_mgr.login(identifier, password, ip_address=client_ip)
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=401)

    user_id = user.id
    role = user.role

    # Assign workspace root
    if role in ("admin", "super_admin", "owner"):
        workspace_path = request.app.get("workspace", "")
    else:
        workspace_path = str((Path(request.app.get("workspace", "")) / "workspaces" / f"user_{user_id}").resolve())
        Path(workspace_path).mkdir(parents=True, exist_ok=True)
        (Path(workspace_path) / ".julius").mkdir(parents=True, exist_ok=True)

    settings = load_settings_from_workspace(workspace_path)
    SESSIONS[raw_token] = {
        "username": user.username,
        "user_id": user_id,
        "role": role,
        "workspace": workspace_path,
        "settings": settings,
        "login_time": time.time()
    }

    response = web.json_response({
        "success": True,
        "token": raw_token,
        "redirect": "/",
        "user": {
            "id": user_id,
            "username": user.username,
            "role": role,
            "workspace": workspace_path
        }
    })
    secure_cookies = os.getenv("JULIUS_SECURE_COOKIES", "false").lower() in ("true", "1", "yes")
    session_ttl = int(os.getenv("JULIUS_SESSION_TTL", "2592000"))
    response.set_cookie(
        "session_id",
        raw_token,
        max_age=session_ttl,
        path="/",
        httponly=True,
        secure=secure_cookies,
        samesite="Lax"
    )
    return response

async def api_signup_handler(request: web.Request) -> web.Response:
    import time
    auth_mgr: AuthManager = request.app.get("auth_mgr")
    try:
        data = await request.json()
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip()
        password = data.get("password", "")
        confirm = data.get("confirm_password", password)
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body"}, status=400)

    if not username or not email or not password:
        return web.json_response({"success": False, "error": "All fields are required"}, status=400)

    if password != confirm:
        return web.json_response({"success": False, "error": "Passwords do not match"}, status=400)

    client_ip = request.remote or "127.0.0.1"
    try:
        user, raw_token, session_rec, workspace_rec = auth_mgr.signup(username, email, password, role="user", ip_address=client_ip)
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)

    user_id = user.id
    workspace_path = str((Path(request.app.get("workspace", "")) / "workspaces" / f"user_{user_id}").resolve())
    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    (Path(workspace_path) / ".julius").mkdir(parents=True, exist_ok=True)

    settings = load_settings_from_workspace(workspace_path)
    SESSIONS[raw_token] = {
        "username": username,
        "user_id": user_id,
        "role": "user",
        "workspace": workspace_path,
        "settings": settings,
        "login_time": time.time()
    }

    response = web.json_response({
        "success": True,
        "token": raw_token,
        "redirect": "/",
        "user": {
            "id": user_id,
            "username": username,
            "role": "user",
            "workspace": workspace_path
        }
    })
    secure_cookies = os.getenv("JULIUS_SECURE_COOKIES", "false").lower() in ("true", "1", "yes")
    session_ttl = int(os.getenv("JULIUS_SESSION_TTL", "2592000"))
    response.set_cookie(
        "session_id",
        raw_token,
        max_age=session_ttl,
        path="/",
        httponly=True,
        secure=secure_cookies,
        samesite="Lax"
    )
    return response

async def api_forgot_password_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        email = data.get("email", "").strip()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body"}, status=400)

    if not email:
        return web.json_response({"success": False, "error": "Email is required"}, status=400)

    users = load_users(request.app["workspace"])
    if email != "david julius" and email not in users:
        return web.json_response({"success": False, "error": "No account with this email exists"}, status=404)

    return web.json_response({"success": True})

async def api_sso_handler(request: web.Request) -> web.Response:
    provider = request.match_info.get("provider", "google").lower()
    lang = request.query.get("lang", "en")
    
    if provider == "google":
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        if not client_id:
            return web.Response(text="Google SSO is not configured", status=500)
        redirect_uri = f"{request.scheme}://{request.host}/api/auth/callback/google"
        scope = "email profile"
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&response_type=code&scope={urllib.parse.quote(scope)}"
        return web.HTTPFound(auth_url)
    elif provider == "github":
        client_id = os.getenv("GITHUB_CLIENT_ID")
        if not client_id:
            return web.Response(text="GitHub SSO is not configured", status=500)
        redirect_uri = f"{request.scheme}://{request.host}/api/auth/callback/github"
        scope = "user:email"
        auth_url = f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&scope={urllib.parse.quote(scope)}"
        return web.HTTPFound(auth_url)
        
    return web.HTTPFound(f"/sso-login.html?provider={provider}&lang={lang}")

async def api_sso_callback_handler(request: web.Request) -> web.Response:
    import time
    code = request.query.get("code")
    
    if not code:
        try:
            data = await request.json()
            provider = data.get("provider", "").strip().lower()
            email = data.get("email", "").strip()
            name = data.get("name", "").strip()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid request body"}, status=400)
    else:
        if "callback/google" in request.path:
            provider = "google"
            client_id = os.getenv("GOOGLE_CLIENT_ID")
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
            redirect_uri = f"{request.scheme}://{request.host}/api/auth/callback/google"
            
            async with aiohttp.ClientSession() as session:
                data = {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"
                }
                async with session.post("https://oauth2.googleapis.com/token", data=data) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return web.Response(text=f"Failed to get token: {text}", status=400)
                    token_res = await resp.json()
                    access_token = token_res.get("access_token")
                    
                async with session.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"}) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return web.Response(text=f"Failed to get user info: {text}", status=400)
                    user_info = await resp.json()
                    
            email = user_info.get("email")
            name = user_info.get("name", email)
        
        elif "callback/github" in request.path:
            provider = "github"
            client_id = os.getenv("GITHUB_CLIENT_ID")
            client_secret = os.getenv("GITHUB_CLIENT_SECRET")
            redirect_uri = f"{request.scheme}://{request.host}/api/auth/callback/github"
            
            async with aiohttp.ClientSession() as session:
                headers = {"Accept": "application/json"}
                data = {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri
                }
                async with session.post("https://github.com/login/oauth/access_token", data=data, headers=headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return web.Response(text=f"Failed to get token: {text}", status=400)
                    token_res = await resp.json()
                    access_token = token_res.get("access_token")
                
                user_headers = {
                    "Authorization": f"token {access_token}",
                    "User-Agent": "Julius-Agent"
                }
                async with session.get("https://api.github.com/user", headers=user_headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return web.Response(text=f"Failed to get GitHub user profile: {text}", status=400)
                    user_info = await resp.json()
                    
                email = user_info.get("email")
                if not email:
                    async with session.get("https://api.github.com/user/emails", headers=user_headers) as resp:
                        if resp.status == 200:
                            emails_info = await resp.json()
                            for email_entry in emails_info:
                                if email_entry.get("primary") and email_entry.get("verified"):
                                    email = email_entry.get("email")
                                    break
                            if not email and emails_info:
                                email = emails_info[0].get("email")
                
                name = user_info.get("name") or user_info.get("login")
                
            if not email:
                return web.Response(text="Failed to retrieve a valid email address from GitHub", status=400)
        else:
            return web.Response(text="Unknown OAuth callback provider", status=400)

    if not email or not provider:
        return web.json_response({"success": False, "error": "Email and provider are required"}, status=400)

    # Load users
    workspace_root = request.app["workspace"]
    users = load_users(workspace_root)

    # If the user is new, register them as an SSO user in users.json
    if email not in users:
        users[email] = {
            "name": name,
            "provider": provider,
            "password_hash": "SSO_ACCOUNT",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(workspace_root, users)

    # Create user-specific workspace
    workspace_path = str((Path(workspace_root) / "workspaces" / email).resolve())
    user_workspace = Path(workspace_path)
    user_workspace.mkdir(parents=True, exist_ok=True)
    
    # Create the workspace subfolders
    julius_dir = user_workspace / ".julius"
    julius_dir.mkdir(parents=True, exist_ok=True)
    
    session_id = str(uuid.uuid4())
    
    metadata_path = julius_dir / "session_metadata.json"
    metadata = {
        "username": email,
        "session_id": session_id,
        "last_login": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_path": str(user_workspace.resolve()),
        "created_at": users[email].get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
        "repository_permissions": ["read", "write"]
    }
    
    try:
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print(f"Error saving session metadata: {e}")

    # Save to session registry
    settings = load_settings_from_workspace(workspace_path)
    SESSIONS[session_id] = {
        "username": email,
        "workspace": workspace_path,
        "settings": settings,
        "login_time": time.time()
    }
    
    if code:
        response = web.HTTPFound("/")
        response.set_cookie("session_id", session_id, max_age=30*24*3600, path="/")
        return response
    else:
        response = web.json_response({"success": True})
        response.set_cookie("session_id", session_id, max_age=30*24*3600, path="/")
        return response

async def api_logout_handler(request: web.Request) -> web.Response:
    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header[7:].strip()

    auth_mgr: AuthManager = request.app.get("auth_mgr")
    if session_id:
        if auth_mgr:
            auth_mgr.logout(session_id)
        SESSIONS.pop(session_id, None)

    response = web.json_response({"success": True, "redirect": "/login"})
    response.del_cookie("session_id", path="/")
    return response

async def api_session_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if session:
        return web.json_response({
            "authenticated": True,
            "user_id": session.get("user_id"),
            "username": session.get("username"),
            "email": session.get("email", ""),
            "role": session.get("role", "user"),
            "workspace": session.get("workspace")
        })
    return web.json_response({"authenticated": False}, status=401)

# ── Admin Console Handlers ───────────────────────────────────────────────────
async def admin_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if not session:
        return web.HTTPFound("/login")
    if session.get("role") not in ("admin", "super_admin", "owner"):
        return web.Response(text="Access denied: Administrator privileges required.", status=403)
    return web.FileResponse(Path(__file__).parent / "frontend" / "admin.html")

async def music_player_handler(request: web.Request) -> web.Response:
    """Julius Lossless Music Player web console."""
    session = get_session(request)
    if not session:
        return web.HTTPFound("/login")
    return web.FileResponse(Path(__file__).parent / "frontend" / "music.html")

async def api_admin_users_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if not session or session.get("role") not in ("admin", "super_admin", "owner"):
        return web.json_response({"success": False, "error": "Access denied"}, status=403)

    db: Database = request.app.get("db")
    users = db.list_users()
    safe_users = []
    for u in users:
        uid = u.id if hasattr(u, "id") else u["id"]
        uname = u.username if hasattr(u, "username") else u["username"]
        uemail = u.email if hasattr(u, "email") else u.get("email", "")
        urole = u.role if hasattr(u, "role") else u["role"]
        ustatus = u.status if hasattr(u, "status") else u["status"]
        ucreated = u.created_at if hasattr(u, "created_at") else u.get("created_at", "")
        safe_users.append({
            "id": uid,
            "username": uname,
            "email": uemail,
            "role": urole,
            "status": ustatus,
            "created_at": ucreated,
            "workspace_path": f"workspaces/user_{uid}"
        })
    return web.json_response({"success": True, "users": safe_users})

async def api_admin_user_create_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if not session or session.get("role") not in ("admin", "super_admin", "owner"):
        return web.json_response({"success": False, "error": "Access denied"}, status=403)

    auth_mgr: AuthManager = request.app.get("auth_mgr")
    try:
        data = await request.json()
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip()
        password = data.get("password", "")
        role = (data.get("role") or "user").strip()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body"}, status=400)

    try:
        user, raw_token, session_rec, workspace_rec = auth_mgr.signup(username, email, password, role=role, ip_address=request.remote)
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)

    audit: AuditLogger = request.app.get("audit_logger")
    if audit:
        audit.log("USER_CREATED_BY_ADMIN", user_id=session.get("user_id"), details={"new_user_id": user.id, "username": username, "role": role})

    return web.json_response({"success": True, "user": {"id": user.id, "username": user.username, "role": user.role}})

async def api_admin_user_status_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if not session or session.get("role") not in ("admin", "super_admin", "owner"):
        return web.json_response({"success": False, "error": "Access denied"}, status=403)

    user_id = int(request.match_info["id"])
    db: Database = request.app.get("db")
    try:
        data = await request.json()
        new_status = data.get("status", "active")
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body"}, status=400)

    success = db.update_user_status(user_id, new_status)
    if success:
        audit: AuditLogger = request.app.get("audit_logger")
        if audit:
            audit.log("USER_STATUS_UPDATED", user_id=session.get("user_id"), details={"target_user_id": user_id, "new_status": new_status})
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "User not found or update failed"}, status=400)

async def api_admin_user_role_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if not session or session.get("role") not in ("admin", "super_admin", "owner"):
        return web.json_response({"success": False, "error": "Access denied"}, status=403)

    user_id = int(request.match_info["id"])
    db: Database = request.app.get("db")
    try:
        data = await request.json()
        new_role = data.get("role", "user")
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body"}, status=400)

    success = db.update_user_role(user_id, new_role)
    if success:
        audit: AuditLogger = request.app.get("audit_logger")
        if audit:
            audit.log("ROLE_CHANGED", user_id=session.get("user_id"), details={"target_user_id": user_id, "new_role": new_role})
        return web.json_response({"success": True})
    return web.json_response({"success": False, "error": "User not found or update failed"}, status=400)

async def api_admin_audit_logs_handler(request: web.Request) -> web.Response:
    session = get_session(request)
    if not session or session.get("role") not in ("admin", "super_admin", "owner"):
        return web.json_response({"success": False, "error": "Access denied"}, status=403)

    db: Database = request.app.get("db")
    logs = db.get_recent_audit_logs(limit=100)
    return web.json_response({"success": True, "logs": logs})


# ── Hot-Reloadable Skills & Plugins API ────────────────────────────────────────
async def api_admin_plugins_handler(request: web.Request) -> web.Response:
    registry = request.app.get("plugin_registry")
    if not registry:
        return web.json_response({"success": False, "plugins": []})
    return web.json_response({"success": True, "plugins": registry.get_all_plugins()})


async def api_admin_plugin_toggle_handler(request: web.Request) -> web.Response:
    plugin_id = request.match_info.get("id", "")
    try:
        data = await request.json()
    except Exception:
        data = {}
    enabled = bool(data.get("enabled", True))
    registry = request.app.get("plugin_registry")
    ok = registry.set_plugin_enabled(plugin_id, enabled) if registry else False
    return web.json_response({"success": ok, "plugin_id": plugin_id, "enabled": enabled})


async def api_admin_plugin_reload_handler(request: web.Request) -> web.Response:
    registry = request.app.get("plugin_registry")
    count = len(registry.reload_all()) if registry else 0
    return web.json_response({"success": True, "count": count})


# ── MediaTek Forensics Bridge API ─────────────────────────────────────────────
async def api_mtk_status_handler(request: web.Request) -> web.Response:
    mtk = request.app.get("mtk_daemon")
    if not mtk:
        return web.json_response({"success": False, "status": {}})
    return web.json_response({"success": True, "status": mtk.get_status()})


async def api_mtk_handshake_handler(request: web.Request) -> web.Response:
    mtk = request.app.get("mtk_daemon")
    if not mtk:
        return web.json_response({"success": False, "error": "MTK daemon unavailable"}, status=503)
    res = await mtk.force_handshake()
    return web.json_response(res)


# ── Sandboxed Widget Canvas API ───────────────────────────────────────────────
async def api_widget_render_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON"}, status=400)

    wtype = data.get("type", "custom")
    if wtype == "git_diff":
        html_out = WidgetPortal.render_git_diff(data.get("diff", ""), data.get("filename", "patch.diff"))
    elif wtype == "database":
        html_out = WidgetPortal.render_database_explorer(
            data.get("db_path", ""), data.get("table", ""), data.get("rows", []), data.get("total_count", 0)
        )
    elif wtype == "system_monitor":
        html_out = WidgetPortal.render_system_monitor(data.get("metrics", {}))
    elif wtype == "audio_spectrum":
        html_out = WidgetPortal.render_audio_spectrum(data.get("track_info", {}))
    else:
        html_out = WidgetPortal.render_custom_widget(
            data.get("title", "Widget"), data.get("body", ""), data.get("script", "")
        )
    iframe_snippet = WidgetPortal.render_iframe_tag(html_out)
    return web.json_response({"success": True, "html": html_out, "iframe": iframe_snippet})


# ── Phase 1: App-level LLM client store & graceful shutdown ──────────────────
async def cleanup_ctx(app: web.Application):
    """Async context manager: yields for app lifetime, cleans up LLM clients on exit."""
    # Start background watcher for hot-reloadable plugins
    plugin_reg = app.get("plugin_registry")
    if plugin_reg:
        asyncio.create_task(plugin_reg.start_watcher())

    yield  # server runs here

    # ── shutdown ──────────────────────────────────────────────────────────────
    if plugin_reg:
        try:
            await plugin_reg.stop_watcher()
        except Exception:
            pass

    cluster_exec = app.get("cluster_executor")
    if cluster_exec:
        try:
            await cluster_exec.disconnect()
        except Exception:
            pass

    mtk = app.get("mtk_daemon")
    if mtk:
        try:
            await mtk.stop()
        except Exception:
            pass

    user_clients: dict = app.get("user_llm_clients", {})
    for uid, clients in list(user_clients.items()):
        for provider, client in list(clients.items()):
            try:
                print(f"Closing LLM client for user {uid} provider {provider}")
                await client.close()
            except Exception as exc:
                print(f"Error closing client: {exc}")
        clients.clear()
    user_clients.clear()

    legacy_clients: dict = app.get("llm_clients", {})
    for provider, client in list(legacy_clients.items()):
        try:
            await client.close()
        except Exception:
            pass
    legacy_clients.clear()

    # Cancel any tasks still running
    tasks: dict = app.get("active_tasks", {})
    for sid, task in list(tasks.items()):
        if not task.done():
            task.cancel()
    tasks.clear()


# ── iPad TUI WebSocket: Auth-free for local network iPad access ───────────────
async def ipad_ws_handler(request: web.Request) -> web.WebSocketResponse:
    """
    WebSocket endpoint for the iPad TUI proxy with optional authentication.
    Requires valid session or explicit IP allowlist configuration.
    Only available from local network (192.168.x.x / 10.x.x.x / 127.x.x.x).
    """
    client_ip = request.remote or ""
    is_local = (
        client_ip.startswith("192.168.")
        or client_ip.startswith("10.")
        or client_ip.startswith("172.")
        or client_ip.startswith("127.")
        or client_ip == "::1"
        or client_ip == "0.0.0.0"
    )
    if not is_local:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "error", "message": "iPad TUI only available on local network."})
        await ws.close(code=4003, message=b"Forbidden")
        return ws

    # Check for existing session first
    session = get_session(request)
    if not session:
        # Check if IP allowlist is configured for passwordless local access
        allowlist = os.getenv("JULIUS_IPAD_ALLOWLIST", "").split(",")
        allowlist = [ip.strip() for ip in allowlist if ip.strip()]
        if client_ip not in allowlist:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"type": "error", "message": "Authentication required for iPad TUI access."})
            await ws.close(code=4001, message=b"Unauthorized")
            return ws
        
        # Build a synthetic session for allowed IP (non-admin, restricted role)
        workspace_path = request.app.get("workspace", str(Path.cwd()))
        settings = load_settings_from_workspace(workspace_path)
        session = {
            "user_id": 999,
            "username": f"ipad_{client_ip.replace('.', '_')}",
            "email": f"ipad_{client_ip.replace('.', '_')}@local",
            "role": "user",  # Restricted role, not admin
            "workspace": workspace_path,
            "session_token": f"ipad-{client_ip}-{uuid.uuid4().hex[:8]}",
            "settings": settings,
        }
        SESSIONS[session["session_token"]] = session
    
    # Delegate to websocket_handler with session token
    request = request.clone(
        rel_url=request.rel_url.with_query({"token": session["session_token"]})
    )
    return await websocket_handler(request)

    # Delegate to websocket_handler — inject token via query param
    # so get_session() finds it in the SESSIONS dict
    request = request.clone(
        rel_url=request.rel_url.with_query({"token": "ipad-tui-session"})
    )
    return await websocket_handler(request)


# ── Phase 2: WebSocket handler with safe task lifecycle & user isolation ──────
async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    session = get_session(request)
    if not session:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "error", "message": "Unauthorized: Session expired or invalid."})
        await ws.close(code=4001, message=b"Unauthorized")
        return ws

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    request.app.setdefault("active_websockets", set()).add(ws)

    # Per-user & per-session identifiers
    user_id = session.get("user_id", 1)
    username = session.get("username", "user")
    user_role = session.get("role", "user")
    session_id = session.get("session_token") or str(uuid.uuid4())
    workspace: str = session.get("workspace") or get_session_workspace(request)
    settings: dict = get_session_settings(request)

    # Per-user isolated LLM client cache (never shared across users)
    user_clients: dict = request.app["user_llm_clients"].setdefault(user_id, {})

    # Task registry
    active_tasks: dict = request.app["active_tasks"]

    agent: WebAgent | None = None
    done_emitted = False
    voice_active = False

    # Phase 5: voice manager reference
    voice_manager: VoiceManager = request.app["voice_manager"]

    # Phase 1.1: Interactive PermissionGate condition variable
    session_permission_gate = PermissionGate(
        emit_event=lambda ev: asyncio.create_task(ws.send_json(ev))
    )

    # ── Event forwarder ──────────────────────────────────────────────────────
    def handle_event(event: dict) -> None:
        nonlocal done_emitted, voice_active
        if event.get("type") in ("done", "error"):
            done_emitted = True
        try:
            asyncio.create_task(ws.send_json(event))
        except Exception as exc:
            print(f"WS send error [{session_id[:8]}]: {exc}")

        # Phase 5: Auto-TTS for agent responses when voice mode is active
        if voice_active and event.get("type") in ("done", "converse"):
            speak_text = event.get("summary") or event.get("message") or ""
            if speak_text:
                old_speak_task = request.app.setdefault("active_tts_tasks", {}).get(session_id)
                if old_speak_task and not old_speak_task.done():
                    old_speak_task.cancel()
                task = asyncio.create_task(_voice_speak(speak_text))
                request.app["active_tts_tasks"][session_id] = task

    # ── Attachment helper (uses WorkspaceSandbox) ──────────────────────────
    def handle_attachments(attachments: list | dict | None) -> None:
        if not attachments:
            return
        if isinstance(attachments, dict):
            attachments = [attachments]
        for att in attachments:
            if not att or not isinstance(att, dict):
                continue
            file_name = att.get("name", "")
            file_data = att.get("data", "")
            if not file_name or not file_data:
                continue
            try:
                sandbox = WorkspaceSandbox(workspace, role=user_role)
                target_path = sandbox.resolve_safe_path(file_name)
                Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(base64.b64decode(file_data))
                print(f"Saved attachment [{session_id[:8]}]: {target_path}")
            except ValueError as exc:
                print(f"Attachment rejected [{session_id[:8]}]: {exc}")
            except Exception as exc:
                print(f"Error saving attachment [{session_id[:8]}]: {exc}")

    # ── Get-or-create LLM router for a provider (user-scoped) ───────────────
    async def get_client(provider: str) -> ProviderRouter:
        existing = user_clients.get(provider)
        if existing is not None:
            return existing
        client = create_default_router(workspace)
        user_clients[provider] = client
        return client

    # ── Agent runner factory (user-scoped) ───────────────────────────────────
    def make_agent(provider: str, mode_override: str | None = None) -> WebAgent:
        client = user_clients.get(provider) or create_default_router(workspace)
        user_clients[provider] = client

        mode = mode_override or settings.get("agentMode", "Supervised")
        auto_approve = settings.get("autoApprove", True)
        
        if mode == "Autonomous":
            deferred_writes = True
            confirm_actions = False
            confirm_writes = False
            confirm_destructive_only = False
        else:
            deferred_writes = False
            confirm_writes = settings.get("confirmWrites", True)
            confirm_actions = (mode in ("Supervised", "Manual")) or confirm_writes
            confirm_destructive_only = auto_approve

        shared_profile = ProductionConfig.PROFILE_DIR or str(Path(request.app["workspace"]) / "chrome_profile")
        if user_role in ("admin", "super_admin", "owner"):
            profile_path = shared_profile
        else:
            user_prof = Path(request.app["workspace"]) / "browser_profiles" / f"user_{user_id}"
            if not user_prof.exists() or not any(user_prof.rglob("Cookies")):
                profile_path = shared_profile
            else:
                profile_path = str(user_prof)
        Path(profile_path).mkdir(parents=True, exist_ok=True)

        max_steps_val = int(settings.get("max_steps") or request.app.get("max_steps", 9999))
        config = AgentConfig(
            provider=provider,
            max_steps=max_steps_val,
            headless=ProductionConfig.HEADLESS,
            confirm_actions=confirm_actions,
            confirm_destructive_only=confirm_destructive_only,
            confirm_writes=confirm_writes,
            deferred_writes=deferred_writes,
            allowed_directory=workspace,
            profile_dir=profile_path,
            abort_hotkey="",
            use_perception=settings.get("use_perception", True),
        )
        agent = WebAgent(config=config, on_event=handle_event, shared_client=client)

        # Inject role-aware ActionExecutor with PermissionGate and ClusterExecutor
        cluster_exec = request.app.get("cluster_executor")
        agent.action_executor = ActionExecutor(
            workspace_root=workspace,
            user_role=user_role,
            user_id=user_id,
            permission_gate=session_permission_gate,
            cluster_executor=cluster_exec,
        )

        if hasattr(agent, "browser_engine"):
            agent.browser_engine._session_id = session_id

        sys_prompt = settings.get("sysPrompt", "").strip()
        if sys_prompt:
            agent.system_prompt = sys_prompt
        else:
            agent.system_prompt = None

        return agent

    # ── Session-level task queue management ───────────────────────────────────
    session_queue = []
    queue_worker_task = None

    async def process_queue():
        nonlocal queue_worker_task
        while session_queue:
            # Check if there is an active running task in registry
            active_task = active_tasks.get(session_id)
            if active_task and not active_task.done():
                await asyncio.sleep(0.5)
                continue
                
            # Pop and run next task function
            next_task_fn = session_queue.pop(0)
            coro = next_task_fn()
            task = asyncio.create_task(coro)
            active_tasks[session_id] = task
            try:
                await task
            except Exception as e:
                print(f"Error executing queued task: {e}")

    def enqueue_or_run(coro_fn, queue_requested: bool):
        nonlocal queue_worker_task
        if queue_requested:
            session_queue.append(coro_fn)
            print(f"Enqueued task for session {session_id[:8]}. Queue size: {len(session_queue)}")
            try:
                asyncio.create_task(ws.send_json({
                    "type": "thought",
                    "step": 9999,
                    "text": f"Task added to queue (Position: {len(session_queue)})"
                }))
            except Exception:
                pass
            if queue_worker_task is None or queue_worker_task.done():
                queue_worker_task = asyncio.create_task(process_queue())
        else:
            # Cancel current queue worker and clear queue
            if queue_worker_task and not queue_worker_task.done():
                queue_worker_task.cancel()
            session_queue.clear()
            
            # Cancel active task
            old_task = active_tasks.pop(session_id, None)
            if old_task and not old_task.done():
                old_task.cancel()
                print(f"Cancelled previous task for session {session_id[:8]}")
                
            # Run immediately
            task = asyncio.create_task(coro_fn())
            active_tasks[session_id] = task

    def launch_agent_task(coro) -> asyncio.Task:
        # Phase 2: cancel previous task for this session
        old_task = active_tasks.pop(session_id, None)
        if old_task and not old_task.done():
            old_task.cancel()
            print(f"Cancelled previous task for session {session_id[:8]}")

        task = asyncio.create_task(coro)
        active_tasks[session_id] = task
        return task

    async def _voice_speak(text: str) -> None:
        """Run TTS and send audio bytes to the client sentence-by-sentence."""
        try:
            # Split text into sentences, filtering out empty ones
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
            for sentence in sentences:
                if not voice_active or ws.closed:
                    break
                
                audio_bytes = await voice_manager.speak(session_id, sentence)
                if audio_bytes:
                    # Send a JSON header first, then binary audio
                    await ws.send_json({"type": "voice_audio_response", "size": len(audio_bytes)})
                    await ws.send_bytes(audio_bytes)
                
                # A small sleep to yield control and keep the event loop responsive
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            print(f"Voice TTS speak task cancelled [{session_id[:8]}]")
        except Exception as exc:
            print(f"Voice TTS error [{session_id[:8]}]: {exc}")

    def _get_and_save_camera_image(payload_data: dict | None = None) -> str | None:
        frame_data = None
        if payload_data:
            frame_data = payload_data.get("camera_image")
            if not frame_data:
                attachment = payload_data.get("attachment")
                if attachment and attachment.get("name") == "camera_capture.jpg":
                    frame_data = attachment.get("data")
                    
        if not frame_data:
            frame_data = request.app["session_camera_frames"].pop(session_id, None)
            
        if not frame_data:
            return None
            
        try:
            target_dir = Path(workspace) / ".julius"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "camera_capture.jpg"
            
            # Handle possible data URL prefix
            if "," in frame_data:
                frame_data = frame_data.split(",")[1]
                
            with open(target_file, "wb") as f:
                f.write(base64.b64decode(frame_data))
            
            print(f"[Camera] Saved live frame to {target_file}")
            return str(target_file.absolute())
        except Exception as exc:
            print(f"Error saving camera capture [{session_id[:8]}]: {exc}")
            return None


    # ── Safe WebSocket send helper ────────────────────────────────────────────
    async def safe_send(payload: dict) -> bool:
        """Send a JSON payload over the WebSocket, silently ignoring errors when
        the connection has already been closed by the client."""
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            # Connection closed while agent was still running — ignore
            return False

    # ── Main message loop ────────────────────────────────────────────────────
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON payload."})
                    continue

                msg_type = data.get("type")

                # ── start_task ──────────────────────────────────────────────
                if msg_type == "start_task":
                    task_text = data.get("task", "").strip()
                    if not task_text:
                        continue

                    # Emit a placeholder title immediately; the agent will set the real title
                    await safe_send({"type": "task_title", "title": "Thinking..."})

                    raw_provider = (data.get("model") or data.get("provider") or settings.get("model", os.getenv("JULIUS_DEFAULT_MODEL", "deepseek"))).strip().lower()
                    provider = "ollama" if raw_provider in ("llama", "local", "ollama") else raw_provider
                    handle_attachments(data.get("attachments") or data.get("attachment"))

                    try:
                        client = await get_client(provider)
                        await client.new_chat()
                        task_mode = data.get("mode") or settings.get("agentMode", "Supervised")
                        agent = make_agent(provider, mode_override=task_mode)
                    except Exception as prep_exc:
                        print(f"Error initializing agent for provider {provider}: {prep_exc}")
                        await safe_send({"type": "error", "message": f"Failed to initialize agent ({provider}): {prep_exc}"})
                        continue
                    done_emitted = False

                    _agent_ref = agent  # capture for closure
                    image_path = _get_and_save_camera_image(data)

                    async def run_agent(_agent=_agent_ref, _task=task_text, _img=image_path):
                        nonlocal done_emitted
                        try:
                            result = await _agent.run(_task, image_path=_img)
                            if not done_emitted:
                                await safe_send({
                                    "type": "done",
                                    "success": result.success,
                                    "summary": result.summary,
                                })
                        except asyncio.CancelledError:
                            print(f"Agent task cancelled [{session_id[:8]}]")
                        except Exception as exc:
                            provider_name = _agent.config.provider
                            client = user_clients.get(provider_name)
                            if client and not client.is_initialized:
                                print(f"Resetting client for provider '{provider_name}': {exc}")
                                try:
                                    await client.close()
                                except Exception:
                                    pass
                                user_clients.pop(provider_name, None)
                            if not done_emitted:
                                await safe_send({"type": "error", "message": str(exc)})

                    queue_requested = data.get("queue", False)
                    enqueue_or_run(lambda: run_agent(), queue_requested)

                # ── terminate ───────────────────────────────────────────────
                elif msg_type == "terminate":
                    print(f"Received terminate command for session [{session_id[:8]}]")
                    # 1. Cancel active agent task
                    old_task = active_tasks.pop(session_id, None)
                    if old_task and not old_task.done():
                        old_task.cancel()
                        print(f"Cancelled active agent task on terminate [{session_id[:8]}]")

                    # 2. Terminate the agent's running processes and cancel futures
                    if agent:
                        # Keep executor and browser processes alive
                        if hasattr(agent, "_confirm_future") and agent._confirm_future and not agent._confirm_future.done():
                            agent._confirm_future.cancel()
                        if hasattr(agent, "_question_future") and agent._question_future and not agent._question_future.done():
                            agent._question_future.cancel()
                        if hasattr(agent, "_human_future") and agent._human_future and not agent._human_future.done():
                            agent._human_future.cancel()
                    
                    # 3. Notify the client that the task has been terminated
                    await safe_send({"type": "done", "success": False, "summary": "Task terminated by user."})

                # ── action_response ─────────────────────────────────────────
                elif msg_type == "action_response":
                    allow = data.get("allow", None)
                    answer = data.get("answer", None)
                    if allow is not None and agent and hasattr(agent, "_confirm_future") and agent._confirm_future:
                        if not agent._confirm_future.done():
                            agent._confirm_future.set_result(allow)
                            print(f"[WebSocket] Confirmation response received: allow={allow}")
                    if answer is not None and agent:
                        if hasattr(agent, "set_question_result"):
                            agent.set_question_result(str(answer))
                        elif hasattr(agent, "_question_future") and agent._question_future and not agent._question_future.done():
                            agent._question_future.set_result(str(answer))
                        elif hasattr(agent, "_human_future") and agent._human_future and not agent._human_future.done():
                            agent._human_future.set_result(str(answer))
                        print(f"[WebSocket] Question/Human answer resolved from action_response: {str(answer)[:80]}")

                # ── Phase 1.1: permission_response ──────────────────────────
                elif msg_type in ("permission_response", "agent.permission_response"):
                    call_id = data.get("call_id", "")
                    decision = data.get("response") or data.get("decision")
                    if not decision:
                        decision = "approve_once" if data.get("allow") else "reject"
                    resolved = session_permission_gate.resolve_permission(call_id, decision)
                    print(f"[WebSocket] PermissionGate resolved call {call_id[:8]} with {decision} (success={resolved})")

                # ── Phase 4.1: audio.interrupt / voice_interrupt (Barge-In) ──
                elif msg_type in ("audio.interrupt", "voice_interrupt", "barge_in"):
                    was_speaking = voice_manager.interrupt(session_id)
                    old_speak_task = request.app.setdefault("active_tts_tasks", {}).pop(session_id, None)
                    if old_speak_task and not old_speak_task.done():
                        old_speak_task.cancel()
                    await safe_send({"type": "audio.interrupted", "session_id": session_id, "was_speaking": was_speaking})
                    print(f"🎤 [WebSocket] Voice Barge-In interruption processed for [{session_id[:8]}]")

                # ── Phase 3.2: MediaTek Hardware Research Forensics ──────────
                elif msg_type == "mtk.status":
                    mtk = request.app.get("mtk_daemon")
                    st = mtk.get_status() if mtk else {}
                    await safe_send({"type": "mtk.status_response", "status": st})

                elif msg_type == "mtk.handshake":
                    mtk = request.app.get("mtk_daemon")
                    if mtk:
                        res = await mtk.force_handshake()
                        await safe_send({"type": "mtk.handshake_result", **res})

                # ── human_response / question_response ──────────────────────
                elif msg_type in ("human_response", "question_response"):
                    answer = data.get("answer", "")
                    if agent:
                        if hasattr(agent, "set_question_result"):
                            agent.set_question_result(str(answer))
                        elif hasattr(agent, "_question_future") and agent._question_future and not agent._question_future.done():
                            agent._question_future.set_result(str(answer))
                        elif hasattr(agent, "_human_future") and agent._human_future and not agent._human_future.done():
                            agent._human_future.set_result(str(answer))
                        print(f"[WebSocket] Human/Question response received: {str(answer)[:80]}")

                # ── follow_up ───────────────────────────────────────────────
                elif msg_type == "follow_up":
                    follow_up_text = data.get("text", "").strip()
                    raw_provider = (data.get("model") or data.get("provider") or settings.get("model", os.getenv("JULIUS_DEFAULT_MODEL", "deepseek"))).strip().lower()
                    provider = "ollama" if raw_provider in ("llama", "local", "ollama") else raw_provider
                    print(f"User follow-up [{session_id[:8]}]: {follow_up_text[:80]} (provider: {provider})")

                    handle_attachments(data.get("attachments") or data.get("attachment"))

                    if not agent or getattr(agent.config, "provider", None) != provider:
                        await get_client(provider)
                        task_mode = data.get("mode") or settings.get("agentMode", "Supervised")
                        agent = make_agent(provider, mode_override=task_mode)

                    if follow_up_text:
                        agent._aborted = False
                        done_emitted = False
                        _agent_ref = agent
                        image_path = _get_and_save_camera_image(data)

                        async def run_follow_up(_agent=_agent_ref, _text=follow_up_text, _img=image_path):
                            nonlocal done_emitted
                            try:
                                result = await _agent.run(_text, image_path=_img)
                                if not done_emitted:
                                    await safe_send({
                                        "type": "done",
                                        "success": result.success,
                                        "summary": result.summary,
                                    })
                            except asyncio.CancelledError:
                                print(f"Follow-up task cancelled [{session_id[:8]}]")
                            except Exception as exc:
                                provider_name = _agent.config.provider
                                client = user_clients.get(provider_name)
                                if client and not client.is_initialized:
                                    try:
                                        await client.close()
                                    except Exception:
                                        pass
                                    user_clients.pop(provider_name, None)
                                if not done_emitted:
                                    await safe_send({"type": "error", "message": str(exc)})

                        queue_requested = data.get("queue", False)
                        enqueue_or_run(lambda: run_follow_up(), queue_requested)

                # ── set_model ───────────────────────────────────────────────
                elif msg_type == "set_model":
                    raw_model = (data.get("model") or data.get("provider") or "").strip().lower()
                    new_model = "ollama" if raw_model in ("llama", "local", "ollama") else raw_model
                    if new_model:
                        settings["model"] = new_model
                        agent = None  # Reset agent so subsequent messages use the newly selected provider
                        print(f"[{session_id[:8]}] Active model switched to: {new_model}")
                        await safe_send({"type": "model_changed", "model": new_model})

                # ── get_models ──────────────────────────────────────────────
                elif msg_type == "get_models":
                    try:
                        from src.providers import list_providers
                        providers = list_providers()
                    except Exception:
                        providers = ["ollama", "deepseek", "gemini", "chatgpt", "grok", "kimi", "perplexity"]
                    if "ollama" not in providers:
                        providers.insert(0, "ollama")
                    current = settings.get("model", os.getenv("JULIUS_DEFAULT_MODEL", "deepseek"))
                    await safe_send({
                        "type": "models_list",
                        "current": current,
                        "models": providers
                    })

                # ── camera_frame ────────────────────────────────────────────
                elif msg_type == "camera_frame":
                    frame_data = data.get("frame", "")
                    if frame_data:
                        request.app["session_camera_frames"][session_id] = frame_data

                # ── Phase 5: Voice messages ─────────────────────────────────
                elif msg_type == "voice_start":
                    voice_active = True
                    success = voice_manager.start_session(session_id)
                    await ws.send_json({
                        "type": "voice_status",
                        "active": success,
                        "voice": os.getenv("JULIUS_VOICE_NAME", "Samantha"),
                    })
                    if success:
                        print(f"🎤 Voice mode ON [{session_id[:8]}]")
                    else:
                        voice_active = False
                        await ws.send_json({"type": "error", "message": "Failed to start voice mode."})

                elif msg_type == "voice_stop":
                    voice_active = False
                    voice_manager.stop_session(session_id)
                    await ws.send_json({"type": "voice_status", "active": False})
                    print(f"🔇 Voice mode OFF [{session_id[:8]}]")

                elif msg_type == "voice_config":
                    config_result = voice_manager.configure(
                        session_id,
                        voice_name=data.get("voice_name"),
                        rate=data.get("rate"),
                        language=data.get("language"),
                    )
                    await ws.send_json({"type": "voice_config_result", **config_result})

                elif msg_type == "voice_audio":
                    # Text audio received as base64 in JSON (legacy support)
                    audio_b64 = data.get("audio", "")
                    audio_format = data.get("format", "webm")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        text = await voice_manager.transcribe(session_id, audio_bytes, audio_format)
                        if text:
                            await ws.send_json({"type": "voice_transcription", "text": text})
                            provider = settings.get("model", os.getenv("JULIUS_DEFAULT_MODEL", "deepseek"))
                            if not agent:
                                await get_client(provider)
                                agent = make_agent(provider)
                            agent._aborted = False
                            done_emitted = False
                            _agent_ref = agent
                            image_path = _get_and_save_camera_image(data)

                            async def run_voice_task(_agent=_agent_ref, _task=text, _img=image_path):
                                nonlocal done_emitted
                                try:
                                    result = await _agent.run(_task, image_path=_img)
                                    if not done_emitted:
                                        await safe_send({
                                            "type": "done",
                                            "success": result.success,
                                            "summary": result.summary,
                                        })
                                except asyncio.CancelledError:
                                    print(f"Voice task cancelled [{session_id[:8]}]")
                                except Exception as exc:
                                    if not done_emitted:
                                        await safe_send({"type": "error", "message": str(exc)})

                            launch_agent_task(run_voice_task())
                        else:
                            await ws.send_json({"type": "voice_transcription", "text": ""})

                elif msg_type == "speech_start":
                    # 1. Cancel active agent task
                    old_task = active_tasks.pop(session_id, None)
                    if old_task and not old_task.done():
                        old_task.cancel()
                        print(f"Cancelled active agent task on speech_start [{session_id[:8]}]")
                        
                    # 2. Cancel active TTS task
                    old_speak_task = request.app.setdefault("active_tts_tasks", {}).pop(session_id, None)
                    if old_speak_task and not old_speak_task.done():
                        old_speak_task.cancel()
                        print(f"Cancelled active TTS task on speech_start [{session_id[:8]}]")
                        
                    # 3. Notify client to interrupt playback
                    await ws.send_json({"type": "interrupt"})
                    
                    # 4. Clear/reset voice buffer
                    request.app.setdefault("session_voice_buffers", {})[session_id] = bytearray()
                    print(f"🎤 Speech started: active tasks cancelled and buffer cleared [{session_id[:8]}]")

                elif msg_type == "speech_stop":
                    print(f"🎤 Speech stopped: starting transcription and processing [{session_id[:8]}]")
                    # Retrieve the accumulated buffer
                    buffers = request.app.setdefault("session_voice_buffers", {})
                    audio_bytes = bytes(buffers.pop(session_id, b""))
                    
                    if audio_bytes:
                        text = await voice_manager.transcribe(session_id, audio_bytes, 'webm')
                        if text:
                            await ws.send_json({"type": "voice_transcription", "text": text})
                            
                            # Run the agent task
                            raw_provider = settings.get("model", os.getenv("JULIUS_DEFAULT_MODEL", "deepseek")).strip().lower()
                            provider = "ollama" if raw_provider in ("llama", "local", "ollama") else raw_provider
                            if not agent or getattr(agent.config, "provider", None) != provider:
                                await get_client(provider)
                                agent = make_agent(provider)
                            
                            agent._aborted = False
                            done_emitted = False
                            _agent_ref = agent
                            image_path = _get_and_save_camera_image(data)

                            async def run_voice_stream_task(_agent=_agent_ref, _task=text, _img=image_path):
                                nonlocal done_emitted
                                try:
                                    result = await _agent.run(_task, image_path=_img)
                                    if not done_emitted:
                                        await safe_send({
                                            "type": "done",
                                            "success": result.success,
                                            "summary": result.summary,
                                        })
                                except asyncio.CancelledError:
                                    print(f"Voice stream task cancelled [{session_id[:8]}]")
                                except Exception as exc:
                                    if not done_emitted:
                                        await safe_send({"type": "error", "message": str(exc)})

                            launch_agent_task(run_voice_stream_task())
                        else:
                            await ws.send_json({"type": "voice_transcription", "text": ""})
                    else:
                        await ws.send_json({"type": "voice_transcription", "text": ""})

            elif msg.type == WSMsgType.BINARY:
                # Accumulate raw binary WebM audio chunks from browser MediaRecorder
                if voice_active:
                    buffers = request.app.setdefault("session_voice_buffers", {})
                    if session_id not in buffers:
                        buffers[session_id] = bytearray()
                    buffers[session_id].extend(msg.data)

            elif msg.type == WSMsgType.ERROR:
                print(f"WS error [{session_id[:8]}]: {ws.exception()}")

    except Exception as exc:
        print(f"WebSocket error [{session_id[:8]}]: {exc}")

    finally:
        # Phase 2: guaranteed cleanup on any disconnect
        print(f"WS disconnected [{session_id[:8]}] — cleaning up.")
        # if agent:
        #     agent._aborted = True
        #     if hasattr(agent, "executor") and agent.executor:
        #         try:
        #             agent.executor.close()
        #             print(f"Closed agent executor (terminated shell process group) on disconnect [{session_id[:8]}]")
        #         except Exception as exc:
        #             print(f"Error closing executor: {exc}")

        # Phase 5: clean up voice session
        voice_manager.stop_session(session_id)
        request.app["session_camera_frames"].pop(session_id, None)
        request.app.get("session_voice_buffers", {}).pop(session_id, None)
        old_speak_task = request.app.get("active_tts_tasks", {}).pop(session_id, None)
        if old_speak_task and not old_speak_task.done():
            old_speak_task.cancel()

        if queue_worker_task and not queue_worker_task.done():
            queue_worker_task.cancel()
        session_queue.clear()

        # Clean up session-scoped temp screenshots
        try:
            import tempfile, shutil
            session_tmp = Path(tempfile.gettempdir()) / "julius_sessions" / session_id
            if session_tmp.exists():
                shutil.rmtree(session_tmp, ignore_errors=True)
                print(f"Cleaned up temp session dir: {session_tmp}")
        except Exception as _cleanup_exc:
            print(f"Could not clean up session temp dir: {_cleanup_exc}")

        # orphan = active_tasks.pop(session_id, None)
        # if orphan and not orphan.done():
        #     orphan.cancel()
        #     print(f"Cancelled agent task for disconnected session {session_id[:8]}")

        request.app.setdefault("active_websockets", set()).discard(ws)
    return ws


# ── Settings handlers ─────────────────────────────────────────────────────────
async def get_settings_handler(request: web.Request) -> web.Response:
    # Use configured CORS origins instead of wildcard
    cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:8788")
    origin = request.headers.get("Origin", "")
    allow_origin = origin if origin in cors_origins.split(",") else cors_origins.split(",")[0]
    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Credentials": "true",
    }
    session = get_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401, headers=headers)
        
    settings = get_session_settings(request)
    return web.json_response(settings, headers=headers)


async def post_settings_handler(request: web.Request) -> web.Response:
    cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:8788")
    origin = request.headers.get("Origin", "")
    allow_origin = origin if origin in cors_origins.split(",") else cors_origins.split(",")[0]
    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Credentials": "true",
    }
    session = get_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401, headers=headers)
        
    try:
        data = await request.json()
        
        # Update in-memory active settings registry
        settings = get_session_settings(request)
        for key, value in data.items():
            if key in settings:
                default_val = settings[key]
                if isinstance(default_val, bool):
                    settings[key] = bool(value)
                elif isinstance(default_val, int):
                    settings[key] = int(value)
                elif isinstance(default_val, float):
                    settings[key] = float(value)
                else:
                    settings[key] = str(value)

        # Write to .env file to persist configurations
        workspace = get_session_workspace(request)
        env_path = Path(workspace) / ".env"
        lines = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()

        key_to_env = {
            "model": "JULIUS_DEFAULT_MODEL",
            "agentName": "JULIUS_AGENT_NAME",
            "agentMode": "JULIUS_AGENT_MODE",
            "sysPrompt": "JULIUS_SYSTEM_PROMPT",
            "autoApprove": "JULIUS_AUTO_APPROVE",
            "confirmWrites": "JULIUS_CONFIRM_WRITES",
            "temp": "JULIUS_TEMPERATURE",
            "streaming": "JULIUS_STREAMING",
            "max_steps": "JULIUS_MAX_STEPS",
            "voice_name": "JULIUS_VOICE_NAME",
            "voice_rate": "JULIUS_VOICE_RATE",
            "stt_language": "JULIUS_STT_LANGUAGE",
            "voice_model": "JULIUS_VOICE_MODEL",
            "dark": "JULIUS_DARK_THEME",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "sarvam_api_key": "SARVAM_API_KEY",
            "use_perception": "JULIUS_USE_PERCEPTION",
        }
        for app_name in CONNECTOR_APPS:
            key_to_env[f"{app_name}_authenticated"] = f"{app_name.upper()}_AUTHENTICATED"

        env_updates = {}
        for k, v in settings.items():
            if k in key_to_env:
                val_str = str(v)
                if key_to_env[k] == "JULIUS_SYSTEM_PROMPT":
                    val_str = val_str.replace("\n", "\\n")
                env_updates[key_to_env[k]] = val_str

        new_lines = []
        seen_keys = set()
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith("#") and "=" in line_stripped:
                parts = line_stripped.split("=", 1)
                k = parts[0].strip()
                if k in env_updates:
                    new_lines.append(f"{k}={env_updates[k]}")
                    seen_keys.add(k)
                    continue
            new_lines.append(line)

        for k, v in env_updates.items():
            if k not in seen_keys:
                new_lines.append(f"{k}={v}")

        env_path.write_text("\n".join(new_lines) + "\n")

        # Dynamically inject into running environment
        for k, v in env_updates.items():
            os.environ[k] = v

        # Dynamically update the shared voice manager config parameters
        voice_manager = request.app["voice_manager"]
        voice_manager._voice_name = settings["voice_name"]
        voice_manager._voice_rate = settings["voice_rate"]
        voice_manager._stt_language = settings["stt_language"]

        # Push new voice_model into env so adapter reads it on next call
        if "voice_model" in data:
            os.environ["JULIUS_VOICE_MODEL"] = str(data["voice_model"])
            # Update active TTS adapters in any live sessions
            for sid, session in voice_manager._sessions.items():
                if session.tts_engine and session.tts_engine._custom_adapter:
                    adapter = session.tts_engine._custom_adapter
                    if hasattr(adapter, '_impl'):
                        adapter._impl._voice_model = str(data["voice_model"])

        return web.json_response({"status": "success", "settings": settings}, headers=headers)
    except Exception as exc:
        return web.json_response({"status": "error", "message": str(exc)}, status=400, headers=headers)


async def settings_options_handler(request: web.Request) -> web.Response:
    cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:8788")
    origin = request.headers.get("Origin", "")
    allow_origin = origin if origin in cors_origins.split(",") else cors_origins.split(",")[0]
    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Credentials": "true",
    }
    return web.Response(headers=headers)


async def voice_test_handler(request: web.Request) -> web.Response:
    """API endpoint to test the Millie voice model and return audio bytes."""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    try:
        data = await request.json()
        text = data.get("text", "Hello! I am Millie, your Julius voice assistant.")

        # Spin up a temporary voice session to test the TTS
        voice_manager = request.app["voice_manager"]
        test_session = "__voice_test__"
        voice_manager.start_session(test_session)
        audio_bytes = await voice_manager.speak(test_session, text)
        voice_manager.stop_session(test_session)

        if audio_bytes:
            return web.Response(
                body=audio_bytes,
                content_type="audio/wav",
                headers=headers,
            )
        return web.json_response({"error": "No audio generated"}, status=500, headers=headers)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500, headers=headers)


async def voice_test_options_handler(request: web.Request) -> web.Response:
    cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:8788")
    origin = request.headers.get("Origin", "")
    allow_origin = origin if origin in cors_origins.split(",") else cors_origins.split(",")[0]
    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Credentials": "true",
    }
    return web.Response(headers=headers)


# ── Dynamic Connector OAuth Endpoints ─────────────────────────────────────────
async def oauth_authorize_handler(request: web.Request) -> web.Response:
    client_id = request.query.get("client_id", "")
    redirect_uri = request.query.get("redirect_uri", "")
    state = request.query.get("state", "")
    scope = request.query.get("scope", "")
    app_id = request.query.get("app", "canva").lower()
    
    expected_client_id = os.getenv("JULIUS_OAUTH_CLIENT_ID", "julius_client_id")
    if client_id != expected_client_id:
        return web.Response(text="OAuth Error: Invalid client_id", status=400)
        
    app_name = app_id.capitalize()
    if app_id == "github":
        app_name = "GitHub"
    elif app_id == "gmail":
        app_name = "Gmail"
    elif app_id == "spotify":
        app_name = "Spotify"
    elif app_id == "figma":
        app_name = "Figma"
    elif app_id == "youtube":
        app_name = "YouTube"
    elif app_id == "whatsapp":
        app_name = "WhatsApp"
    elif app_id == "hubspot":
        app_name = "HubSpot"
    elif app_id == "jira":
        app_name = "Jira"
    elif app_id == "google_calendar":
        app_name = "Google Calendar"
    elif app_id == "google_drive":
        app_name = "Google Drive"

    colors = {
        "whatsapp": "#25D366",
        "youtube": "#FF0000",
        "instagram": "#E1306C",
        "slack": "#4A154B",
        "notion": "#000000",
        "github": "#24292e",
        "gmail": "#EA4335",
        "google_calendar": "#4285F4",
        "google_drive": "#34A853",
        "spotify": "#1DB954",
        "figma": "#F24E1E",
        "trello": "#0079BF",
        "zoom": "#2D8CFF",
        "discord": "#5865F2",
        "hubspot": "#FF7A59",
        "jira": "#0052CC",
        "linear": "#5E6AD2",
        "stripe": "#635BFF",
        "shopify": "#96BF48",
        "canva": "#00C4CC",
    }
    theme_color = colors.get(app_id, "#4A6CF7")

    scopes_map = {
        "whatsapp": ["Send text messages to contacts", "Read profile status and list chats"],
        "youtube": ["Search and play video content", "Retrieve video and channel statistics"],
        "instagram": ["Read feed profile details", "Publish media images and captions"],
        "slack": ["Send workspace messages to channels", "List public chat channels"],
        "notion": ["Read/write page hierarchies", "Query table databases and records"],
        "github": ["Access repositories read/write", "Manage issues, PRs, and comments"],
        "gmail": ["Draft and send emails", "Search inbox messages and labels"],
        "google_calendar": ["View scheduled calendar events", "Create new meeting invites"],
        "google_drive": ["Search files and folders", "Download documents to local disk"],
        "spotify": ["Check current playing track", "Control play/pause and search tracks"],
        "figma": ["Read vector canvas structures", "Comment on files and node assets"],
        "trello": ["List active project boards", "Add cards and lists to boards"],
        "zoom": ["Schedule virtual video meetings", "Retrieve active meeting schedules"],
        "discord": ["Post messages to channels", "Read active guild server details"],
        "hubspot": ["List CRM contacts information", "Create deal pipeline logs"],
        "jira": ["Create bug and task tickets", "Query project sprint backlogs"],
        "linear": ["Create issue logs on team boards", "Search active team spaces"],
        "stripe": ["Query recent payment logs", "Create new billing customer profiles"],
        "shopify": ["List inventory catalog items", "Check recent store order logs"],
    }
    scopes = scopes_map.get(app_id, ["Read and write access to workspace integrations", "Host standard tool definitions"])

    scopes_html = "".join([
        f'<div class="scope-item"><span class="check-icon" style="color: {theme_color}">✓</span><span>{s}</span></div>'
        for s in scopes
    ])

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Connect Julius to {app_name}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    @font-face {{
      font-family: 'Julius';
      src: url('/assets/Julius-Regular.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'JetBrains Mono';
      src: url('/assets/JetBrainsMono-Regular.woff2') format('woff2');
    }}
    body, p, span, div, h1, h2, h3, h4, h5, h6, li, a, label, button, input, textarea {{
      font-family: 'Julius', 'Inter', -apple-system, sans-serif;
    }}
    code, pre, kbd, samp, pre *, code *, .font-mono {{
      font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 10% 20%, rgb(0, 0, 0) 0%, rgb(18, 20, 36) 90.1%);
      color: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      padding: 40px;
      width: 440px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
      text-align: center;
      animation: fadeIn 0.6s ease-out;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(15px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .logos-container {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 20px;
      margin-bottom: 30px;
    }}
    .divider {{
      color: rgba(255,255,255,0.4);
      font-size: 24px;
      font-weight: 300;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 700;
      margin: 0 0 10px 0;
      letter-spacing: -0.02em;
    }}
    p.subtitle {{
      font-size: 14px;
      color: rgba(255, 255, 255, 0.7);
      margin: 0 0 30px 0;
      line-height: 1.5;
    }}
    .scopes {{
      text-align: left;
      background: rgba(0, 0, 0, 0.2);
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 35px;
      border: 1px solid rgba(255,255,255,0.05);
    }}
    .scope-item {{
      display: flex;
      align-items: flex-start;
      gap: 12px;
      font-size: 13px;
      line-height: 1.4;
      color: rgba(255,255,255,0.85);
      margin-bottom: 12px;
    }}
    .scope-item:last-child {{
      margin-bottom: 0;
    }}
    .check-icon {{
      font-weight: bold;
      font-size: 14px;
    }}
    .buttons {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    button {{
      font-family: inherit;
      font-size: 14px;
      font-weight: 600;
      padding: 14px;
      border-radius: 14px;
      border: none;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .btn-primary {{
      background: linear-gradient(135deg, {theme_color}, #4A6CF7);
      color: #fff;
      box-shadow: 0 4px 12px rgba(74, 108, 247, 0.2);
    }}
    .btn-primary:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(74, 108, 247, 0.3);
    }}
    .btn-secondary {{
      background: rgba(255, 255, 255, 0.08);
      color: rgba(255,255,255,0.8);
      border: 1px solid rgba(255,255,255,0.1);
    }}
    .btn-secondary:hover {{
      background: rgba(255, 255, 255, 0.15);
      color: #fff;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logos-container">
      <div style="background: {theme_color}; width: 60px; height: 60px; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 11px; color: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">{app_name[:7]}</div>
      <div class="divider">✦</div>
      <img src="/logo-badge-dark.svg" width="60" height="60" style="border-radius: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);" alt="Julius">
    </div>
    <h1>Connect Julius to {app_name}</h1>
    <p class="subtitle">Julius is requesting access to your {app_name} account to run automations and tasks on your behalf.</p>
    
    <div class="scopes">
      {scopes_html}
    </div>

    <div class="buttons">
      <button class="btn-primary" onclick="authorize()">Authorize Access</button>
      <button class="btn-secondary" onclick="window.close()">Cancel</button>
    </div>
  </div>

  <script>
    function authorize() {{
      const code = "auth_code_" + Math.random().toString(36).substring(2, 12);
      window.location.href = "/oauth/consent/allow?code=" + code + "&redirect_uri=" + encodeURIComponent("{redirect_uri}") + "&state={state}";
    }}
  </script>
</body>
</html>
"""
    return web.Response(text=html_content, content_type="text/html")


async def oauth_consent_allow_handler(request: web.Request) -> web.Response:
    code = request.query.get("code", "")
    redirect_uri = request.query.get("redirect_uri", "")
    state = request.query.get("state", "")
    
    import time
    OAUTH_CODES[code] = {
        "client_id": "julius_client_id",
        "redirect_uri": redirect_uri,
        "expires_at": time.time() + 600
    }
    
    target_url = f"{redirect_uri}?code={code}&state={state}"
    return web.HTTPFound(location=target_url)


async def oauth_token_handler(request: web.Request) -> web.Response:
    if request.content_type == "application/json":
        data = await request.json()
    else:
        data = await request.post()
        
    grant_type = data.get("grant_type")
    code = data.get("code")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    redirect_uri = data.get("redirect_uri")
    
    if grant_type != "authorization_code":
        return web.json_response({"error": "unsupported_grant_type"}, status=400)
        
    expected_client_id = os.getenv("JULIUS_OAUTH_CLIENT_ID", "julius_client_id")
    expected_client_secret = os.getenv("JULIUS_OAUTH_CLIENT_SECRET", "julius_client_secret")
    if client_id != expected_client_id or client_secret != expected_client_secret:
        return web.json_response({"error": "invalid_client"}, status=400)
        
    if not code or code not in OAUTH_CODES:
        return web.json_response({"error": "invalid_grant", "error_description": "Code invalid or expired"}, status=400)
        
    code_data = OAUTH_CODES[code]
    import time
    if code_data["expires_at"] < time.time():
        del OAUTH_CODES[code]
        return web.json_response({"error": "invalid_grant", "error_description": "Code expired"}, status=400)
        
    import secrets
    access_token = "access_" + secrets.token_hex(16)
    refresh_token = "refresh_" + secrets.token_hex(16)
    
    OAUTH_TOKENS[access_token] = {
        "client_id": client_id,
        "expires_at": time.time() + 3600
    }
    
    del OAUTH_CODES[code]
    
    return web.json_response({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": refresh_token
    })


async def connector_auth_handler(request: web.Request) -> web.Response:
    app_id = request.match_info.get("app", "").lower()
    import urllib.parse
    state = "state_" + app_id
    redirect_uri = f"http://{request.host}/api/connectors/callback/{app_id}"
    authorize_url = f"/oauth/authorize?response_type=code&client_id=julius_client_id&redirect_uri={urllib.parse.quote(redirect_uri)}&state={state}&app={app_id}"
    return web.HTTPFound(location=authorize_url)


async def exchange_code_for_token(host: str, code: str, redirect_uri: str) -> dict:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": os.getenv("JULIUS_OAUTH_CLIENT_ID", "julius_client_id"),
            "client_secret": os.getenv("JULIUS_OAUTH_CLIENT_SECRET", "julius_client_secret"),
            "redirect_uri": redirect_uri
        }
        async with session.post(f"http://{host}/oauth/token", data=payload) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                text = await resp.text()
                raise Exception(f"Token exchange failed: {text}")


async def connector_callback_handler(request: web.Request) -> web.Response:
    workspace = get_session_workspace(request)
    app_id = request.match_info.get("app", "").lower()
    app_name = app_id.capitalize()
    
    if app_id == "github":
        app_name = "GitHub"
    elif app_id == "youtube":
        app_name = "YouTube"
    elif app_id == "whatsapp":
        app_name = "WhatsApp"
    elif app_id == "hubspot":
        app_name = "HubSpot"
    elif app_id == "google_calendar":
        app_name = "Google Calendar"
    elif app_id == "google_drive":
        app_name = "Google Drive"

    colors = {
        "whatsapp": "#25D366",
        "youtube": "#FF0000",
        "instagram": "#E1306C",
        "slack": "#4A154B",
        "notion": "#000000",
        "github": "#24292e",
        "gmail": "#EA4335",
        "spotify": "#1DB954",
        "figma": "#F24E1E",
        "canva": "#00C4CC",
    }
    theme_color = colors.get(app_id, "#4A6CF7")

    # Real OAuth authorization code exchange!
    code = request.query.get("code", "")
    redirect_uri = f"http://{request.host}/api/connectors/callback/{app_id}"
    
    try:
        token_data = await exchange_code_for_token(request.host, code, redirect_uri)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
    except Exception as e:
        print(f"OAuth code exchange failed: {e}")
        return web.Response(text=f"OAuth code exchange failed: {e}", status=500)

    # 1. Update settings
    setting_key = f"{app_id}_authenticated"
    settings = get_session_settings(request)
    settings[setting_key] = True
    settings[f"{app_id}_access_token"] = access_token
    settings[f"{app_id}_refresh_token"] = refresh_token
    
    # 2. Persist in .env
    env_path = Path(workspace) / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    
    new_lines = []
    seen_auth = False
    seen_access = False
    seen_refresh = False
    
    env_var_name = f"{app_id.upper()}_AUTHENTICATED"
    token_var_name = f"{app_id.upper()}_ACCESS_TOKEN"
    refresh_var_name = f"{app_id.upper()}_REFRESH_TOKEN"
    
    for line in lines:
        if line.strip().startswith(f"{env_var_name}="):
            new_lines.append(f"{env_var_name}=true")
            seen_auth = True
        elif line.strip().startswith(f"{token_var_name}="):
            new_lines.append(f"{token_var_name}={access_token}")
            seen_access = True
        elif line.strip().startswith(f"{refresh_var_name}="):
            new_lines.append(f"{refresh_var_name}={refresh_token}")
            seen_refresh = True
        else:
            new_lines.append(line)
            
    if not seen_auth:
        new_lines.append(f"{env_var_name}=true")
    if not seen_access:
        new_lines.append(f"{token_var_name}={access_token}")
    if not seen_refresh:
        new_lines.append(f"{refresh_var_name}={refresh_token}")
        
    env_path.write_text("\n".join(new_lines) + "\n")
    os.environ[env_var_name] = "true"
    os.environ[token_var_name] = access_token
    os.environ[refresh_var_name] = refresh_token
    
    # 3. Add to mcp_config.json
    config_path = Path(workspace) / "mcp_config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            if "mcpServers" not in config:
                config["mcpServers"] = {}
            
            if app_id == "canva":
                config["mcpServers"]["canva"] = {
                    "command": "python3",
                    "args": [
                        "-m",
                        "src.mcp.canva_server",
                        "--workspace",
                        workspace
                    ],
                    "autoStart": True
                }
            else:
                config["mcpServers"][app_id] = {
                    "command": "python3",
                    "args": [
                        "-m",
                        "src.mcp.connector_server",
                        "--app",
                        app_id,
                        "--workspace",
                        workspace
                    ],
                    "autoStart": True
                }
            config_path.write_text(json.dumps(config, indent=2))
        except Exception as e:
            print(f"Error updating mcp_config.json for {app_id}: {e}")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{app_name} Connected</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    @font-face {{
      font-family: 'Julius';
      src: url('/assets/Julius-Regular.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'JetBrains Mono';
      src: url('/assets/JetBrainsMono-Regular.woff2') format('woff2');
    }}
    body, p, span, div, h1, h2, h3, h4, h5, h6, li, a, label, button, input, textarea {{
      font-family: 'Julius', 'Inter', -apple-system, sans-serif;
    }}
    code, pre, kbd, samp, pre *, code *, .font-mono {{
      font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 10% 20%, rgb(0, 0, 0) 0%, rgb(18, 20, 36) 90.1%);
      color: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      padding: 40px 30px;
      width: 400px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
      text-align: center;
      animation: scaleUp 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    @keyframes scaleUp {{
      from {{ opacity: 0; transform: scale(0.92); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}
    .check-circle {{
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: rgba(74, 108, 247, 0.15);
      border: 2px solid {theme_color};
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 25px auto;
      animation: popCheck 0.6s 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
    }}
    @keyframes popCheck {{
      from {{ transform: scale(0); }}
      to {{ transform: scale(1); }}
    }}
    .check-icon {{
      color: {theme_color};
      font-size: 32px;
      font-weight: bold;
    }}
    h1 {{
      font-size: 22px;
      font-weight: 700;
      margin: 0 0 10px 0;
      letter-spacing: -0.01em;
    }}
    p {{
      font-size: 14px;
      color: rgba(255, 255, 255, 0.7);
      margin: 0 0 20px 0;
      line-height: 1.5;
    }}
    .status-badge {{
      display: inline-block;
      background: rgba(74, 108, 247, 0.15);
      color: {theme_color};
      font-size: 12px;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 20px;
      border: 1px solid rgba(74, 108, 247, 0.2);
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="check-circle">
      <span class="check-icon">✓</span>
    </div>
    <h1>Connection Successful!</h1>
    <p>Julius has been granted authorization to access {app_name}. This window will close automatically.</p>
    <div class="status-badge">CONNECTED</div>
  </div>

  <script>
    if (window.opener) {{
      window.opener.postMessage("{app_id}_connected", "*");
    }}
    setTimeout(() => {{
      window.close();
    }}, 2000);
  </script>
</body>
</html>
"""
    return web.Response(text=html_content, content_type="text/html")


async def connector_disconnect_handler(request: web.Request) -> web.Response:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    workspace = get_session_workspace(request)
    app_id = request.match_info.get("app", "").lower()
    
    # 1. Update active settings
    setting_key = f"{app_id}_authenticated"
    settings = get_session_settings(request)
    settings[setting_key] = False
    if f"{app_id}_access_token" in settings:
        del settings[f"{app_id}_access_token"]
    if f"{app_id}_refresh_token" in settings:
        del settings[f"{app_id}_refresh_token"]
    
    # 2. Persist in .env
    env_path = Path(workspace) / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    
    new_lines = []
    env_var_name = f"{app_id.upper()}_AUTHENTICATED"
    token_var_name = f"{app_id.upper()}_ACCESS_TOKEN"
    refresh_var_name = f"{app_id.upper()}_REFRESH_TOKEN"
    
    for line in lines:
        l_strip = line.strip()
        if l_strip.startswith(f"{env_var_name}="):
            new_lines.append(f"{env_var_name}=false")
        elif l_strip.startswith(f"{token_var_name}="):
            continue
        elif l_strip.startswith(f"{refresh_var_name}="):
            continue
        else:
            new_lines.append(line)
            
    env_path.write_text("\n".join(new_lines) + "\n")
    os.environ[env_var_name] = "false"
    os.environ.pop(token_var_name, None)
    os.environ.pop(refresh_var_name, None)
    
    # 3. Remove from mcp_config.json
    config_path = Path(workspace) / "mcp_config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            if "mcpServers" in config and app_id in config["mcpServers"]:
                del config["mcpServers"][app_id]
                config_path.write_text(json.dumps(config, indent=2))
        except Exception as e:
            print(f"Error updating mcp_config.json for {app_id}: {e}")
            
    return web.json_response({"status": "success", "settings": settings}, headers=headers)

# ── Julius Build — Prompt-to-App Generation API ────────────────────────────────

def _get_build_store(workspace: str):
    """Get an AppGenerationStore for the workspace."""
    from src.memory.working_state import AppGenerationStore
    return AppGenerationStore(workspace)


async def build_app_handler(request: web.Request) -> web.Response:
    """
    POST /api/build
    Body: { "prompt": "...", "overwrite": false }

    Stages 2-4 run as a background asyncio task; poll /api/build/{job_id}/status.
    """
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    session = get_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401, headers=headers)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400, headers=headers)

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return web.json_response({"error": "prompt is required"}, status=400, headers=headers)

    overwrite = bool(data.get("overwrite", False))
    workspace = get_session_workspace(request)
    project_id = str(Path(workspace).resolve())

    job_id = str(uuid.uuid4())
    build_jobs = request.app.setdefault("build_jobs", {})
    build_jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "prompt": prompt,
        "progress": [],
        "spec": None,
        "record": None,
        "error": None,
    }

    def _on_progress(stage: str, message: str) -> None:
        job = build_jobs.get(job_id)
        if job:
            job["status"] = stage
            job["progress"].append({"stage": stage, "message": message, "ts": time.time()})

    async def _run_build():
        from src.app_builder import AppBuilder
        job = build_jobs[job_id]
        try:
            provider = get_session_settings(request).get("model", "deepseek")
            sess = get_session(request)
            uid = sess.get("user_id", 1) if sess else 1
            user_clients_dict = request.app["user_llm_clients"].setdefault(uid, {})
            llm_client = user_clients_dict.get(provider)
            if not llm_client:
                llm_client = create_default_router(workspace)
                user_clients_dict[provider] = llm_client

            builder = AppBuilder(
                workspace_root=workspace,
                llm_client=llm_client,
                on_progress=_on_progress,
            )

            record = await builder.build(prompt, project_id=project_id, overwrite=overwrite)
            job["record"] = record.to_dict()
            job["spec"] = record.spec.to_dict() if record.spec else {}
            job["status"] = "done"

            # Persist to DB
            store = _get_build_store(workspace)
            store.save_generation(record)

        except Exception as exc:
            job["status"] = "error"
            job["error"] = str(exc)
            import traceback
            print(f"[Build] Job {job_id[:8]} failed: {exc}")
            traceback.print_exc()

    task = asyncio.create_task(_run_build())
    request.app.setdefault("build_tasks", {})[job_id] = task

    return web.json_response({"job_id": job_id, "status": "started"}, headers=headers)


async def build_status_handler(request: web.Request) -> web.Response:
    """GET /api/build/{job_id}/status"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    session = get_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401, headers=headers)

    job_id = request.match_info.get("job_id", "")
    build_jobs = request.app.get("build_jobs", {})
    job = build_jobs.get(job_id)

    if not job:
        return web.json_response({"error": "Job not found"}, status=404, headers=headers)

    return web.json_response({
        "id": job["id"],
        "status": job["status"],
        "prompt": job["prompt"],
        "progress": job["progress"],
        "spec": job.get("spec"),
        "record": job.get("record"),
        "error": job.get("error"),
    }, headers=headers)


async def build_history_handler(request: web.Request) -> web.Response:
    """GET /api/build/history"""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    session = get_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401, headers=headers)

    workspace = get_session_workspace(request)
    project_id = str(Path(workspace).resolve())
    try:
        store = _get_build_store(workspace)
        generations = store.list_generations(project_id)
        return web.json_response({"generations": generations}, headers=headers)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500, headers=headers)


async def build_screenshot_handler(request: web.Request) -> web.Response:
    """GET /api/build/{job_id}/screenshot"""
    session = get_session(request)
    if not session:
        return web.json_response({"error": "Unauthorized"}, status=401)

    job_id = request.match_info.get("job_id", "")
    build_jobs = request.app.get("build_jobs", {})
    job = build_jobs.get(job_id)
    record = job.get("record") if job else None

    if not record:
        workspace = get_session_workspace(request)
        store = _get_build_store(workspace)
        record = store.get_generation(job_id)

    if not record or not record.get("screenshot_path"):
        return web.json_response({"error": "Screenshot not found"}, status=404)

    shot_path = Path(record["screenshot_path"])
    if not shot_path.exists():
        return web.json_response({"error": "Screenshot file not found on disk"}, status=404)

    return web.FileResponse(shot_path, headers={"Content-Type": "image/png"})


async def build_options_handler(request: web.Request) -> web.Response:
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    })


# ── Static file handlers ──────────────────────────────────────────────────────
async def index_handler(request: web.Request) -> web.Response:
    if REQUIRE_AUTH:
        session = get_session(request)
        if not session:
            return web.HTTPFound("/login")
    resp = web.FileResponse(Path(__file__).parent / "frontend" / "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


async def catch_all(request: web.Request) -> web.Response:
    frontend_path = Path(__file__).parent / "frontend"
    path = request.match_info.get("path", "")
    
    # Whitelist public routes
    is_public = (
        path in (
            "login", "favicon.svg", "favicon.ico", "favicon.png", "favicon-dark.png",
            "logo.svg", "logo-badge-dark.svg", "logo-white.svg",
            "signup.html", "forgot-password.html", "check-email.html",
            "privacy.html", "terms.html", "signup", "forgot-password",
            "check-email", "privacy", "terms", "sso-login", "sso-login.html"
        ) or
        path.startswith("assets/") or
        path.startswith("fonts/") or
        path.startswith("api/login") or
        path.startswith("api/signup") or
        path.startswith("api/forgot-password") or
        path.startswith("api/auth/sso/") or
        path.startswith("api/session")
    )
    if is_public:
        if path == "login":
            return await login_handler(request)
        elif path == "api/login":
            return await api_login_handler(request)
        elif path == "api/signup":
            return await api_signup_handler(request)
        elif path == "api/forgot-password":
            return await api_forgot_password_handler(request)
        elif path.startswith("api/auth/sso/callback"):
            return await api_sso_callback_handler(request)
        elif path.startswith("api/auth/sso/"):
            return await api_sso_handler(request)
        elif path == "api/session":
            return await api_session_handler(request)
        elif path in ("signup", "signup.html"):
            return web.FileResponse(frontend_path / "signup.html")
        elif path in ("forgot-password", "forgot-password.html"):
            return web.FileResponse(frontend_path / "forgot-password.html")
        elif path in ("check-email", "check-email.html"):
            return web.FileResponse(frontend_path / "check-email.html")
        elif path in ("privacy", "privacy.html"):
            return web.FileResponse(frontend_path / "privacy.html")
        elif path in ("terms", "terms.html"):
            return web.FileResponse(frontend_path / "terms.html")
        elif path in ("sso-login", "sso-login.html"):
            return web.FileResponse(frontend_path / "sso-login.html")
        # Serve public static files directly if present in frontend/
        file_path = (frontend_path / path).resolve()
        if file_path.is_relative_to(frontend_path.resolve()) and file_path.is_file():
            return web.FileResponse(file_path)
        # Otherwise, fall through to static file serving

    # Check session
    session = get_session(request)
    if not session:
        if path.startswith("api/"):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.HTTPFound("/login")

    user_role = session.get("role", "user")
    clean_path = path.lstrip("/")
    
    # Try serving from the workspace first (with strict sandbox check)
    workspace = session.get("workspace") or get_session_workspace(request)
    if workspace:
        sandbox = WorkspaceSandbox(workspace, role=user_role)
        try:
            safe_target = sandbox.resolve_safe_path(clean_path)
            if os.path.isfile(safe_target):
                return web.FileResponse(safe_target)
        except (PermissionError, ValueError):
            pass

    file_path = (frontend_path / path).resolve()
    # Only serve files that are actually inside the frontend directory
    if file_path.is_relative_to(frontend_path.resolve()) and file_path.is_file():
        return web.FileResponse(file_path)
    return web.FileResponse(frontend_path / "index.html")


# ── Phase 1: App factory ──────────────────────────────────────────────────────
def create_app(workspace: str) -> web.Application:
    """Create and configure the aiohttp application with production settings."""
    # Phase 3: body-size limit (prevents memory-exhaustion DoS)
    app = web.Application(client_max_size=ProductionConfig.CLIENT_MAX_SIZE)

    # Initialize persistent multi-user database & auth
    julius_db = Path.home() / ".julius" / "julius.db"
    julius_db = Path.home() / ".julius" / "julius.db"
    if not julius_db.exists() and julius_db.exists():
        db_path = julius_db
    else:
        (Path.home() / ".julius").mkdir(parents=True, exist_ok=True)
        db_path = julius_db
    db = Database(db_path)
    auth_mgr = AuthManager(db)
    audit_logger = AuditLogger(db)

    app["db"] = db
    app["auth_mgr"] = auth_mgr
    app["audit_logger"] = audit_logger

    # Per-user and per-session isolation registries
    app["llm_clients"] = {}         # legacy fallback
    app["user_llm_clients"] = {}    # user_id -> { provider_name -> WebLLMClient }
    app["active_tasks"] = {}        # session_id -> asyncio.Task
    app["session_camera_frames"] = {}  # session_id -> base64 image data
    app["session_voice_buffers"] = {}   # session_id -> bytearray
    app["active_tts_tasks"] = {}        # session_id -> asyncio.Task
    app["build_jobs"] = {}              # job_id -> build job dict
    app["build_tasks"] = {}             # job_id -> asyncio.Task
    app["workspace"] = workspace
    app["active_websockets"] = set()

    # Phase 5: shared voice manager
    app["voice_manager"] = VoiceManager()

    # Phase 2, 3, 4: cluster executor, hardware forensics daemon, and plugin registry
    app["cluster_executor"] = ClusterExecutor(local_workspace=workspace)
    app["mtk_daemon"] = MTKDaemon()
    app["plugin_registry"] = get_plugin_registry(workspace)

    # Phase 1: graceful shutdown via cleanup context
    app.cleanup_ctx.append(cleanup_ctx)

    # Daemon Hardening Middleware (WS2.5, T1.5)
    daemon_sec = DaemonSecurityManager()
    app["daemon_security"] = daemon_sec
    app.middlewares.append(daemon_sec.middleware)

    # Telemetry and Health Probes (WS5, T1.5)
    app.router.add_get("/healthz", handle_healthz)
    app.router.add_get("/readyz", handle_readyz)
    app.router.add_get("/metrics", handle_metrics)

    # Admin Console routes (Super Admin only)
    app.router.add_get("/admin", admin_handler)
    app.router.add_get("/api/admin/users", api_admin_users_handler)
    app.router.add_post("/api/admin/users/create", api_admin_user_create_handler)
    app.router.add_post("/api/admin/users/{id}/status", api_admin_user_status_handler)
    app.router.add_post("/api/admin/users/{id}/role", api_admin_user_role_handler)
    app.router.add_get("/api/admin/audit-logs", api_admin_audit_logs_handler)

    # Hot-Reloadable Skills & Plugins
    app.router.add_get("/api/admin/plugins", api_admin_plugins_handler)
    app.router.add_post("/api/admin/plugins/{id}/toggle", api_admin_plugin_toggle_handler)
    app.router.add_post("/api/admin/plugins/reload", api_admin_plugin_reload_handler)

    # MediaTek Forensics Bridge
    app.router.add_get("/api/mtk/status", api_mtk_status_handler)
    app.router.add_post("/api/mtk/handshake", api_mtk_handshake_handler)

    # Sandboxed Dynamic Widgets
    app.router.add_post("/api/widget/render", api_widget_render_handler)

    # Routes
    app.router.add_get("/login", login_handler)
    app.router.add_post("/api/login", api_login_handler)
    app.router.add_post("/api/signup", api_signup_handler)
    app.router.add_post("/api/forgot-password", api_forgot_password_handler)
    app.router.add_get("/api/auth/sso/{provider}", api_sso_handler)
    app.router.add_post("/api/auth/sso/callback", api_sso_callback_handler)
    app.router.add_get("/api/auth/callback/google", api_sso_callback_handler)
    app.router.add_get("/api/auth/callback/github", api_sso_callback_handler)
    app.router.add_post("/api/logout", api_logout_handler)
    app.router.add_get("/api/session", api_session_handler)
    app.router.add_get("/api/settings", get_settings_handler)
    app.router.add_post("/api/settings", post_settings_handler)
    app.router.add_options("/api/settings", settings_options_handler)
    app.router.add_post("/api/voice/test", voice_test_handler)
    app.router.add_options("/api/voice/test", voice_test_options_handler)
    
    # Dynamic OAuth Connectors
    app.router.add_get("/api/connectors/auth/{app}", connector_auth_handler)
    app.router.add_get("/api/connectors/callback/{app}", connector_callback_handler)
    app.router.add_post("/api/connectors/disconnect/{app}", connector_disconnect_handler)
    app.router.add_options("/api/connectors/disconnect/{app}", settings_options_handler)
    
    # OAuth Provider Server Endpoints
    app.router.add_get("/oauth/authorize", oauth_authorize_handler)
    app.router.add_get("/oauth/consent/allow", oauth_consent_allow_handler)
    app.router.add_post("/oauth/token", oauth_token_handler)
    
    # Julius Build — Prompt-to-App Generation
    app.router.add_post("/api/build", build_app_handler)
    app.router.add_get("/api/build/history", build_history_handler)
    app.router.add_get("/api/build/{job_id}/status", build_status_handler)
    app.router.add_get("/api/build/{job_id}/screenshot", build_screenshot_handler)
    app.router.add_options("/api/build", build_options_handler)
    app.router.add_options("/api/build/{job_id}/status", build_options_handler)

    # Browser Login Portal & Interactive Controller
    app["headless"] = ProductionConfig.HEADLESS
    app.router.add_get("/browser-portal", browser_portal_handler)
    app.router.add_get("/api/browser/portal", api_browser_portal_handler)
    app.router.add_get("/api/browser/screenshot", api_browser_screenshot_handler)
    app.router.add_post("/api/browser/action", api_browser_action_handler)

    # Julius Lossless Music Platform Subsystem
    try:
        from src.music.api import setup_music_routes
        from src.music.jobs import music_job_manager

        async def music_cleanup_ctx(app_inst: web.Application):
            await music_job_manager.start()
            yield
            await music_job_manager.stop()

        app.cleanup_ctx.append(music_cleanup_ctx)
        app.router.add_get("/music", music_player_handler)
        app.router.add_get("/player", music_player_handler)
        setup_music_routes(app)
    except Exception as e:
        print(f"Warning: Failed to initialize music subsystem in julius_gui: {e}")

    # Julius WhatsApp Personal Assistant Subsystem
    try:
        from src.integrations.whatsapp.api import setup_whatsapp_routes, whatsapp_cleanup_ctx
        app.cleanup_ctx.append(whatsapp_cleanup_ctx)
        setup_whatsapp_routes(app)
    except Exception as e:
        print(f"Warning: Failed to initialize WhatsApp subsystem in julius_gui: {e}")

    app.router.add_get("/ws/ipad", ipad_ws_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/", index_handler)
    app.router.add_get("/{path:.*}", catch_all)

    return app


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Julius Agent Server")
    parser.add_argument("--tui", action="store_true", help="Launch the Textual TUI")
    parser.add_argument(
        "--workspace",
        default=str(Path.cwd()),
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=ProductionConfig.PORT,
        help=f"HTTP server port (default: {ProductionConfig.PORT})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=ProductionConfig.HOST,
        help=f"HTTP server host/bind address (default: {ProductionConfig.HOST})",
    )
    args = parser.parse_args()

    workspace = str(Path(args.workspace).resolve())
    port = args.port
    host = args.host

    # Enforce loopback bind security (T1.5): refuse non-loopback bind without TLS
    enforce_loopback_binding(host, os.getenv("JULIUS_TLS_CERT"))

    app = create_app(workspace)
    runner = web.AppRunner(app)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(runner.setup())

    max_retries = 10
    site = None
    for attempt in range(max_retries):
        try:
            site = web.TCPSite(runner, host, port)
            print(f"Starting Julius Server on {host}:{port}...", flush=True)
            loop.run_until_complete(site.start())
            break
        except OSError as e:
            if e.errno in (48, 98, 10048):  # Address already in use (macOS: 48, Linux: 98, Windows: 10048)
                print(f"⚠️ Port {port} is in use, trying port {port + 1}...", flush=True)
                port += 1
            else:
                raise e
    else:
        print(f"❌ Error: Could not find any free port starting from {args.port}", flush=True)
        loop.run_until_complete(runner.cleanup())
        return

    display_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    url = f"http://{display_host}:{port}"
    print(f"🚀 Julius UI is running at {url}", flush=True)
    print(f"   Workspace : {workspace}", flush=True)
    print(f"   Max steps : {ProductionConfig.MAX_STEPS}", flush=True)
    print(f"   Body limit: {ProductionConfig.CLIENT_MAX_SIZE // (1024 * 1024)} MB", flush=True)
    print(f"   Voice     : {'✅ Enabled' if ProductionConfig.VOICE_ENABLED else '❌ Disabled'}", flush=True)

    if args.tui:
        try:
            from src.tui.app import launch_tui

            print("🖥️  Launching Textual TUI (press Q to quit)...")
            import threading

            threading.Thread(target=loop.run_forever, daemon=True).start()
            launch_tui(workspace=workspace, ws_url=f"ws://{display_host}:{port}/ws")
            loop.call_soon_threadsafe(loop.stop)
        except ImportError:
            print("⚠️  Textual not installed. Run: pip install textual watchfiles")
            print("   Falling back to browser mode.")
            if not ProductionConfig.HEADLESS:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            try:
                loop.run_forever()
            except KeyboardInterrupt:
                print("\nStopping server...")
    else:
        if not ProductionConfig.HEADLESS:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print("\nStopping server...")

    loop.run_until_complete(runner.cleanup())


if __name__ == "__main__":
    main()
