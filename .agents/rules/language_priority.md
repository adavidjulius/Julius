# Strict Language Priority Rule

1. **TypeScript is Highest Priority**:
   - Every agent operating in Julius must write new code in **TypeScript (`.ts` / `.tsx`) first**.
   - All TUI components, user-facing UI, frontend apps, widgets, and developer utilities must be built in TypeScript.
   - Ongoing work on `src/tui_ts/` must continue incrementally using React/Ink and the Julius theme tokens.

2. **Python is Secondary Priority**:
   - Python is reserved strictly for existing core backend pipelines, agent execution loops, and OS subprocess operations where the virtual environment is currently rooted.
   - New feature development or UI expansion should NOT default to Python when TypeScript can be used.

3. **Cursor Standard**:
   - All interfaces must display a normal cursor (standard arrow pointer and normal block cursor), never an I-beam text-selection cursor on general app surfaces.

