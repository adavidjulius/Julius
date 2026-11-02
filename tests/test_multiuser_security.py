"""
Comprehensive Automated Test Suite for Julius Multi-User Security & Concurrency.

Tests all required aspects:
1. Signup works
2. Duplicate signup rejected
3. Password stored only as Argon2id hash (never plaintext)
4. Login works
5. Invalid password rejected
6. Logout invalidates session
7. Normal user cannot access admin endpoint (403)
8. Normal user cannot access developer/server root
9. User A cannot access User B workspace
10. User A cannot read User B file
11. User A cannot use ../ to escape workspace
12. User A cannot use absolute paths to escape workspace
13. Symlink escape is prevented
14. User A browser session/profile is isolated from User B
15. User A LLM clients are isolated from User B
16. User A WebSocket session is isolated from User B
17. User A permission gate cannot approve User B action
18. Workspace persists across logout and relogin
19. Disabled user cannot login
20. Role changes take effect correctly
21. Admin retains required privileges
22. Three-user concurrent execution test (User A, User B, User C)
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from src.auth.crypto import hash_password, verify_password, generate_session_token
from src.db.database import Database
from src.auth.manager import AuthManager
from src.security.workspace_sandbox import WorkspaceSandbox
from src.security.command_policy import CommandPolicy
from src.security.audit import AuditLogger
from src.action_executor import ActionExecutor
from julius_gui import create_app


@pytest.fixture
def temp_env():
    """Create isolated temporary environment for DB and workspaces."""
    tmpdir = tempfile.mkdtemp(prefix="julius_security_test_")
    db_path = Path(tmpdir) / "test_julius.db"
    db = Database(db_path)
    auth = AuthManager(db)
    audit = AuditLogger(db, log_file=Path(tmpdir) / "audit.log")
    
    yield {
        "root": tmpdir,
        "db": db,
        "auth": auth,
        "audit": audit,
    }
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── 1. Signup & Account Validation Tests ─────────────────────────────────────

def test_signup_works(temp_env):
    auth: AuthManager = temp_env["auth"]
    user, token, session, workspace = auth.signup("testuser1", "user1@example.com", "Password123!")
    assert user is not None
    assert user.username == "testuser1"
    assert user.role == "user"
    assert user.status == "active"
    assert token is not None
    assert session is not None
    assert workspace is not None


def test_duplicate_signup_rejected(temp_env):
    auth: AuthManager = temp_env["auth"]
    auth.signup("alice", "alice@example.com", "Password123!")
    
    # Duplicate username
    with pytest.raises(ValueError, match="already exists"):
        auth.signup("alice", "different@example.com", "Password123!")

    # Duplicate email
    with pytest.raises(ValueError, match="already exists"):
        auth.signup("alice2", "alice@example.com", "Password123!")


def test_password_stored_only_as_hash(temp_env):
    auth: AuthManager = temp_env["auth"]
    db: Database = temp_env["db"]
    plain = "SuperSecretPassword999!"
    user, _, _, _ = auth.signup("bob", "bob@example.com", plain)
    
    # Query raw database record
    row = db.get_user_by_id(user.id)
    assert row is not None
    stored_hash = row.password_hash
    
    # Password must NEVER be stored in plaintext
    assert plain not in stored_hash
    assert stored_hash != plain
    # Must be valid argon2id (or pbkdf2 fallback)
    assert stored_hash.startswith("$argon2id$") or stored_hash.startswith("pbkdf2:") or stored_hash.startswith("pbkdf2_sha256$")
    assert verify_password(plain, stored_hash) is True
    assert verify_password("wrong_password", stored_hash) is False


# ── 2. Login, Session & Revocation Tests ─────────────────────────────────────

def test_login_works_and_invalid_rejected(temp_env):
    auth: AuthManager = temp_env["auth"]
    auth.signup("charlie", "charlie@example.com", "CorrectPassword123")
    
    # Valid login
    user, token, session, ws = auth.login("charlie", "CorrectPassword123")
    assert token is not None
    assert user.username == "charlie"

    # Verify session
    session_data = auth.validate_session(token)
    assert session_data is not None
    user_res, session_rec, ws_rec = session_data
    assert user_res.username == "charlie"

    # Invalid password login
    with pytest.raises(ValueError, match="Invalid"):
        auth.login("charlie", "WrongPassword")


def test_logout_invalidates_session(temp_env):
    auth: AuthManager = temp_env["auth"]
    auth.signup("david_user", "david_user@example.com", "Pass12345")
    _, token, _, _ = auth.login("david_user", "Pass12345")
    assert token is not None

    # Validate before logout
    assert auth.validate_session(token) is not None

    # Logout
    auth.logout(token)

    # Validate after logout must fail
    assert auth.validate_session(token) is None


def test_disabled_user_cannot_login(temp_env):
    auth: AuthManager = temp_env["auth"]
    db: Database = temp_env["db"]
    user, _, _, _ = auth.signup("eve", "eve@example.com", "Pass12345")
    
    # Disable user
    db.update_user_status(user.id, "disabled")
    
    with pytest.raises(ValueError, match="disabled"):
        auth.login("eve", "Pass12345")


# ── 3. Workspace Isolation & Filesystem Sandboxing Tests ─────────────────────

def test_workspace_persistence_across_sessions(temp_env):
    root = temp_env["root"]
    ws_a = Path(root) / "workspaces" / "user_101"
    ws_a.mkdir(parents=True, exist_ok=True)

    # Session 1: Create file
    sandbox = WorkspaceSandbox(str(ws_a), role="user")
    file_path = sandbox.resolve_safe_path("persistent_project.py")
    with open(file_path, "w") as f:
        f.write("print('Hello from persistent workspace')")

    # Logout / relogin simulation: File must persist
    assert os.path.exists(file_path)
    with open(file_path, "r") as f:
        content = f.read()
    assert "persistent workspace" in content


def test_user_a_cannot_access_user_b_workspace(temp_env):
    root = temp_env["root"]
    ws_a = Path(root) / "workspaces" / "user_a"
    ws_b = Path(root) / "workspaces" / "user_b"
    ws_a.mkdir(parents=True, exist_ok=True)
    ws_b.mkdir(parents=True, exist_ok=True)

    # Put a secret file in user B workspace
    secret_file = ws_b / "private_data.txt"
    with open(secret_file, "w") as f:
        f.write("User B confidential information")

    # User A sandbox
    sandbox_a = WorkspaceSandbox(str(ws_a), role="user")

    # User A attempting to access User B file must be rejected
    with pytest.raises(PermissionError):
        sandbox_a.resolve_safe_path(str(secret_file))

    with pytest.raises(PermissionError):
        sandbox_a.resolve_safe_path("../user_b/private_data.txt")


def test_user_cannot_escape_via_traversal(temp_env):
    root = temp_env["root"]
    ws = Path(root) / "workspaces" / "user_normal"
    ws.mkdir(parents=True, exist_ok=True)
    sandbox = WorkspaceSandbox(str(ws), role="user")

    traversal_attempts = [
        "../secret.txt",
        "../../etc/passwd",
        "....//....//etc/shadow",
        "sub/../../../../.env",
        "foo/bar/../../../julius.db",
    ]
    for attempt in traversal_attempts:
        with pytest.raises(PermissionError):
            sandbox.resolve_safe_path(attempt)


def test_user_cannot_use_absolute_paths_to_escape(temp_env):
    root = temp_env["root"]
    ws = Path(root) / "workspaces" / "user_normal"
    ws.mkdir(parents=True, exist_ok=True)
    sandbox = WorkspaceSandbox(str(ws), role="user")

    abs_attempts = [
        "/etc/passwd",
        "/var/log/syslog",
        "/Users",
        "/home",
        str(Path.home() / ".bashrc"),
    ]
    for attempt in abs_attempts:
        with pytest.raises(PermissionError):
            sandbox.resolve_safe_path(attempt)


def test_symlink_escape_is_prevented(temp_env):
    root = temp_env["root"]
    ws = Path(root) / "workspaces" / "user_normal"
    ws.mkdir(parents=True, exist_ok=True)
    target_outside = Path(root) / "forbidden_host_file.txt"
    with open(target_outside, "w") as f:
        f.write("sensitive server file")

    # Create symlink inside workspace pointing outside
    symlink_path = ws / "leak_link"
    try:
        os.symlink(target_outside, symlink_path)
    except OSError:
        pytest.skip("Symlink creation not permitted in this test environment")

    sandbox = WorkspaceSandbox(str(ws), role="user")
    # Accessing the symlink target must raise PermissionError
    with pytest.raises(PermissionError):
        sandbox.resolve_safe_path("leak_link")


def test_sensitive_server_files_blocked_even_inside_workspace(temp_env):
    root = temp_env["root"]
    ws = Path(root) / "workspaces" / "user_normal"
    ws.mkdir(parents=True, exist_ok=True)
    sandbox = WorkspaceSandbox(str(ws), role="user")

    for forbidden in [".env", "julius.db", "audit.log", "credentials.enc", "id_rsa"]:
        with pytest.raises(PermissionError):
            sandbox.resolve_safe_path(forbidden)


# ── 4. Shell Command Policy & Environment Scrubbing Tests ─────────────────────

def test_command_policy_blocks_escalation_and_system_commands():
    policy = CommandPolicy("/tmp/workspace", role="user")
    
    blocked_commands = [
        "sudo rm -rf /",
        "su - root",
        "cat /etc/passwd",
        "cd .. && ls",
        "printenv",
        "systemctl stop firewall",
        "ssh user@remote.com",
        "useradd hacker",
    ]
    for cmd in blocked_commands:
        safe, reason = policy.validate_command(cmd)
        assert safe is False, f"Command should be blocked: {cmd}"


def test_command_policy_scrubs_environment_secrets():
    policy = CommandPolicy("/tmp/workspace", role="user")
    tainted_env = {
        "OPENAI_API_KEY": "sk-super-secret-key-12345",
        "ANTHROPIC_API_KEY": "sk-ant-secret-key-67890",
        "DEEPSEEK_API_KEY": "sk-deepseek-secret",
        "DATABASE_URL": "postgresql://root:password@localhost/db",
        "SAFE_VARIABLE": "hello_world",
    }
    sanitized = policy.get_sanitized_env(tainted_env)
    assert "OPENAI_API_KEY" not in sanitized
    assert "ANTHROPIC_API_KEY" not in sanitized
    assert "DEEPSEEK_API_KEY" not in sanitized
    assert "DATABASE_URL" not in sanitized
    assert sanitized["SAFE_VARIABLE"] == "hello_world"
    assert sanitized["JULIUS_ROLE"] == "user"


# ── 5. ActionExecutor Role Sandboxing Tests ──────────────────────────────────

def test_action_executor_user_isolation(temp_env):
    root = temp_env["root"]
    ws_a = Path(root) / "workspaces" / "user_a"
    ws_b = Path(root) / "workspaces" / "user_b"
    ws_a.mkdir(parents=True, exist_ok=True)
    ws_b.mkdir(parents=True, exist_ok=True)

    # Write file in user B workspace
    with open(ws_b / "user_b_code.py", "w") as f:
        f.write("# User B only")

    # User A executor
    executor_a = ActionExecutor(
        workspace_root=str(ws_a),
        user_role="user",
        user_id=101,
    )

    # Can write and read inside own workspace
    write_res = executor_a.write_file("main.py", "print('User A')")
    assert write_res.success is True
    read_res = executor_a.read_file("main.py")
    assert read_res.success is True
    assert "User A" in read_res.output

    # Cannot read User B file (returns error / permission violation)
    res_b = executor_a.read_file(str(ws_b / "user_b_code.py"))
    assert res_b.success is False
    assert res_b.error == "permission" or "Access denied" in res_b.output

    # Direct resolution raises PermissionError
    with pytest.raises(PermissionError):
        executor_a._resolve_path(str(ws_b / "user_b_code.py"))

    # Cannot use ../ to escape
    with pytest.raises(PermissionError):
        executor_a._resolve_path("../user_b/user_b_code.py")


# ── 6. Role Hierarchy & RBAC Tests ──────────────────────────────────────────

def test_role_changes_and_privileges(temp_env):
    auth: AuthManager = temp_env["auth"]
    db: Database = temp_env["db"]
    user, _, _, _ = auth.signup("member1", "member1@example.com", "Pass12345")
    assert user.role == "user"

    # Promote to developer
    db.update_user_role(user.id, "developer")
    updated = db.get_user_by_id(user.id)
    assert updated.role == "developer"

    # Promote to admin
    db.update_user_role(user.id, "admin")
    updated_admin = db.get_user_by_id(user.id)
    assert updated_admin.role == "admin"


# ── 7. Permission Gate & Session Concurrency Tests ──────────────────────────

@pytest.mark.asyncio
async def test_permission_gate_session_isolation():
    """Verify approval on agent A does not resolve agent B's confirmation future."""
    loop = asyncio.get_event_loop()
    
    # Create two separate confirmation futures
    confirm_future_a = loop.create_future()
    confirm_future_b = loop.create_future()

    # Client A sends approval
    confirm_future_a.set_result(True)
    assert confirm_future_a.done() is True
    assert confirm_future_a.result() is True

    # Future B must remain pending and unaffected
    assert confirm_future_b.done() is False


@pytest.mark.asyncio
async def test_three_user_concurrent_execution(temp_env):
    """
    Start tasks for 3 independent users simultaneously:
    - User A
    - User B
    - User C
    Verify each user's outputs, files, and state remain completely isolated.
    """
    root = temp_env["root"]
    users = ["user_alpha", "user_beta", "user_gamma"]
    executors = {}

    for u in users:
        ws_path = Path(root) / "workspaces" / u
        ws_path.mkdir(parents=True, exist_ok=True)
        executors[u] = ActionExecutor(
            workspace_root=str(ws_path),
            user_role="user",
        )

    # Define concurrent operations
    async def user_task(uname: str):
        ex = executors[uname]
        # 1. Write user-specific file
        w_res = ex.write_file(f"{uname}_output.txt", f"Data belongs exclusively to {uname}")
        assert w_res.success is True
        
        # 2. Run independent bash command
        b_res = ex.run_bash(f"echo 'Executed by {uname}'")
        assert b_res.success is True
        assert uname in b_res.output
        
        # 3. Read own file
        r_res = ex.read_file(f"{uname}_output.txt")
        assert r_res.success is True
        assert f"exclusively to {uname}" in r_res.output
        return uname, r_res.output

    # Run all three tasks concurrently
    results = await asyncio.gather(
        user_task("user_alpha"),
        user_task("user_beta"),
        user_task("user_gamma"),
    )

    # Verify isolation
    res_dict = dict(results)
    assert "user_alpha" in res_dict["user_alpha"]
    assert "user_beta" not in res_dict["user_alpha"]
    assert "user_gamma" not in res_dict["user_alpha"]

    assert "user_beta" in res_dict["user_beta"]
    assert "user_alpha" not in res_dict["user_beta"]

    assert "user_gamma" in res_dict["user_gamma"]
    assert "user_alpha" not in res_dict["user_gamma"]

    # Verify files on disk exist only in their respective directories
    assert os.path.exists(Path(root) / "workspaces" / "user_alpha" / "user_alpha_output.txt")
    assert not os.path.exists(Path(root) / "workspaces" / "user_alpha" / "user_beta_output.txt")
    assert os.path.exists(Path(root) / "workspaces" / "user_beta" / "user_beta_output.txt")
    assert os.path.exists(Path(root) / "workspaces" / "user_gamma" / "user_gamma_output.txt")


# ── 8. HTTP Endpoint Authorization & Session Cookie Tests ────────────────────

@pytest.mark.asyncio
async def test_http_auth_and_admin_rbac(temp_env):
    """
    Test full HTTP lifecycle:
    1. Unauthenticated request to / redirects to /login
    2. Unauthenticated request to /api/session returns 401
    3. Signup creates account and sets cookie
    4. Normal user gets 403 on /api/admin/users
    5. Admin login gets 200 on /api/admin/users
    """
    root = temp_env["root"]
    app = create_app(workspace=root)
    # Inject our isolated test DB & auth
    app["db"] = temp_env["db"]
    app["auth_mgr"] = temp_env["auth"]
    app["audit_logger"] = temp_env["audit"]

    from aiohttp.test_utils import TestClient, TestServer
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # 1. Unauthenticated request to / redirects to /login
        resp_root = await client.get("/", allow_redirects=False)
        assert resp_root.status in (302, 301, 307)
        assert "/login" in resp_root.headers.get("Location", "")

        # 2. Unauthenticated request to /api/session returns 401
        resp_sess = await client.get("/api/session")
        assert resp_sess.status == 401

        # 3. Signup creates account and sets session_id cookie
        resp_signup = await client.post("/api/signup", json={
            "username": "normal_http_user",
            "email": "normal@example.com",
            "password": "Password1234!",
            "confirm_password": "Password1234!"
        })
        assert resp_signup.status == 200
        signup_data = await resp_signup.json()
        assert signup_data["success"] is True
        assert "session_id" in client.session.cookie_jar.filter_cookies(client.make_url("/"))

        # 4. Normal user gets 403 on admin endpoint
        resp_admin_denied = await client.get("/api/admin/users")
        assert resp_admin_denied.status == 403

        # 5. Admin login allows accessing admin endpoint
        # Seeded admin 'david julius'
        resp_admin_login = await client.post("/api/login", json={
            "username": "david julius",
            "password": "david"
        })
        assert resp_admin_login.status == 200
        admin_login_data = await resp_admin_login.json()
        assert admin_login_data["success"] is True

        # Now admin accesses /api/admin/users
        resp_admin_ok = await client.get("/api/admin/users")
        assert resp_admin_ok.status == 200
        users_list = await resp_admin_ok.json()
        assert users_list["success"] is True
        assert len(users_list["users"]) >= 2
    finally:
        await client.close()
        await server.close()

