# Julius Security Policy & Threat Model (WS2.8)

## 1. Security Philosophy & Invariants

Julius is built upon three non-negotiable security principles:
1. **Deny by default**: Every tool call, shell command, and filesystem operation passes through a centralized policy engine. Unknown or unconfigured actions are refused.
2. **Fail closed**: If any security scanner, secrets filter, or policy evaluator encounters an error, the operation is blocked immediately.
3. **Local-first verification**: Secrets never leave the local machine, and telemetry is strictly opt-in.

---

## 2. STRIDE Threat Model

| Component | Threat Category | Identified Threat | Mitigation in Julius |
|---|---|---|---|
| **Local Daemon** (`juliusd.py`) | Spoofing & Tampering | DNS-rebinding attacks where external web origin calls `http://localhost:8000` | Loopback-only bind (`127.0.0.1`), per-install random bearer tokens, strict `Host` and `Origin` header validation against loopback whitelist. Non-loopback binds refused without TLS and auth. |
| **Agent Execution Loop** | Elevation of Privilege | Untrusted repository prompts driving malicious shell commands (`sudo`, `curl \| sh`, tampering with git hooks) | AST-based shell parsing blocks privilege escalations, dangerous commands, and `.git/hooks` modifications. Scoped sandbox tiers confine execution to workspace blast radius. |
| **Plugins & MCP Servers** | Information Disclosure & Elevation | Third-party plugin processes inheriting host secrets and API keys | Isolated child processes executed with scrubbed environments (`JULIUS_ISOLATED_PLUGIN=1`), capability manifests, and Ed25519 signature verification. |
| **Outbound LLM Prompts** | Information Disclosure | Confidential credentials (API keys, private keys, JWTs) accidentally included in outbound prompts or indexed into PKB | Four-choke-point redaction: PKB indexing, LLM outbound context (DLP scan), application logs, and audit payloads. |
| **Audit Log** | Repudiation | Attacker rewrites or alters local audit records | Cryptographic HMAC-SHA256 chained ledger with keys stored in the OS Keychain, canonical JSON serialization, and signed Ed25519 checkpoints. |
| **Auto-Updater** | Tampering | Malicious or hijacked update payload delivered over network | Updates verified via Ed25519 digital signatures and SHA-256 hashes against signed manifests; atomic file swap with automated rollback on launch failure. |

---

## 3. Reporting a Vulnerability

We welcome security vulnerability reports from the community and security researchers.

### Reporting Channel
- **Email**: `meetjuliusai@gmail.com` (or file a confidential GitHub Security Advisory).
- **Encryption**: You may encrypt your report using our security team's PGP/Ed25519 key.

### Response SLAs
- **Initial Acknowledgement**: Within 24 hours.
- **Triage & Severity Assessment**: Within 48 hours.
- **Remediation & Patch Target**: Critical vulnerabilities patched within 7 business days; high vulnerabilities within 14 business days.

### Safe Harbor
Activities conducted in good faith within the scope of this policy will be considered authorized conduct, and we will not initiate legal action against researchers for accidental, good-faith violations.

