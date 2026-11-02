# Julius Standard Error Code Reference (WS10)

All subsystem exceptions in Julius inherit from `JuliusError` and emit standardized machine-readable error codes (`JUL-xxx`) accompanied by actionable remediation hints.

---

## Provider Errors (`JUL-PROV`)

| Code | Meaning | Cause | Actionable Hint |
|---|---|---|---|
| `JUL-PROV-001` | Auth Failed | Invalid API key or expired token | Check your API key in `~/.julius/config.toml` or OS Keychain. |
| `JUL-PROV-002` | Rate Limited | HTTP 429 quota reached | Router will apply exponential backoff. Configure fallback provider in settings. |
| `JUL-PROV-003` | Timeout | Network read or connect timeout | Verify internet connectivity or proxy configuration. |
| `JUL-PROV-004` | Context Too Large | Prompt exceeds model context cap | Reduce conversation history or enable automated context compaction. |
| `JUL-PROV-005` | Provider Unavailable | HTTP 5xx server outage | The router will trip the circuit breaker and attempt configured fallback. |

---

## Policy & Sandbox Errors (`JUL-POL`)

| Code | Meaning | Cause | Actionable Hint |
|---|---|---|---|
| `JUL-POL-001` | Path Denied | File path escapes workspace blast radius | Confine file operations to workspace or request a scoped path grant. |
| `JUL-POL-002` | Approval Required | Action requires explicit user confirmation | Confirm the action prompt in terminal or GUI. |
| `JUL-POL-003` | Hard-Deny Path | Attempted access to critical system path | Paths matching `~/.ssh/**` or `/etc/shadow` are permanently forbidden. |
| `JUL-POL-004` | Command Forbidden | Command pattern blocked by shell guard | Privilege escalation (`sudo`) and remote pipe-to-shell patterns are blocked. |
| `JUL-POL-005` | Taint Restriction | Untrusted content present in context | While untrusted data is in context, autonomy is downgraded for safety. |

---

## Configuration Errors (`JUL-CFG`)

| Code | Meaning | Cause | Actionable Hint |
|---|---|---|---|
| `JUL-CFG-001` | Invalid Setting | Pydantic schema validation error | Run `julius config validate` to inspect schema issues. |
| `JUL-CFG-002` | Missing Key | Required configuration setting absent | Run `julius --setup` or inspect `.julius/config.toml`. |

---

## Database Errors (`JUL-DB`)

| Code | Meaning | Cause | Actionable Hint |
|---|---|---|---|
| `JUL-DB-001` | Migration Failed | Forward schema migration failed | Database was automatically rolled back to pre-migration backup. |
| `JUL-DB-002` | Integrity Check Failed | PRAGMA quick_check returned error | Restore database from latest backup using `julius restore`. |
| `JUL-DB-003` | Database Locked | SQLite busy timeout exceeded | Ensure idle maintenance processes are completed. |

---

## Agent Loop Errors (`JUL-AGT`)

| Code | Meaning | Cause | Actionable Hint |
|---|---|---|---|
| `JUL-AGT-001` | Budget Exceeded | Task step or token limit reached | Increase `budgets.max_steps` or `budgets.max_tokens` in settings. |
| `JUL-AGT-002` | Loop Detected | Identical tool call repeated N times | Agent stopped runaway cycle. Intervene with new guidance. |

---

## License Errors (`JUL-LIC`)

| Code | Meaning | Cause | Actionable Hint |
|---|---|---|---|
| `JUL-LIC-001` | License Expired | Subscription expired past grace period | Renew license at julius.ai/pricing. |
| `JUL-LIC-002` | Invalid Signature | License file altered or corrupted | Re-download your digital license file from your account portal. |

