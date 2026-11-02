# Julius Web Interface — Prerequisites Foundation

This directory houses the foundational prerequisites and cross-platform scaffolding for the **Julius Web Interface**. The project is structured in TypeScript and configured to connect with the broader Julius ecosystem without altering core engine files.

---

## 🛠️ Prerequisites Built

1. **Architecture & Skill Contract**:
   - Skill documentation located in [`.agents/skills/julius-web-interface/SKILL.md`](../.agents/skills/julius-web-interface/SKILL.md).
   - Non-invasive reading of brand books, tokens, hardware profiles (Rockchip RK3126 / P200), and REST/WebSocket APIs.
2. **Design Tokens & Fonts**:
   - Base design tokens defined in `css/julius.css` and `src/theme/tokens.ts` (`#121214`, `#1c1c1e`, `#c8b896`, `#006A25`, `#731a1a`).
   - Font assets in `fonts/` (`Julius-Regular.woff2`, `Julius-Bold.woff2`).
3. **API & Hardware Bridges**:
   - Dual-mode connector in `src/services/juliusApi.ts` connecting to `http://localhost:8000` (FastAPI `julius_dashboard_api`).
   - Sandboxed widget runtime host bridge in `js/widget-runtime.js` (`window.JuliusWidgetHost`, `julius:sendPrompt`).
   - Audio & haptics synthesis service in `src/services/soundHaptics.ts`.
4. **Dev Server & Launchers**:
   - `server.py`: Standard library Python HTTP server with `/api/` proxying to port 8000.
   - `run_web_interface.bat` & `run_web_interface.ps1`: 1-click startup scripts.
   - `package.json` & `tsconfig.json`: TypeScript configuration.

---

## 🚀 Running the Prerequisites Server
```powershell
python server.py --open
```
or run `run_web_interface.bat`.
