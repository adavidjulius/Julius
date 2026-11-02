# Julius Test Code Isolation Rule

## Testing & Directory Rules
1. **Dedicated Test Directory (`Julius_Test`)**:
   - All experimental test programs, standalone verification scripts, test benches, and test harnesses must be saved inside the `Julius_Test/` folder.
   - Tests are purely for verification and validation.

2. **Zero Core Dependency on Tests**:
   - The core codebase (`src/`, entrypoints like `run_agent.py`, `julius_gui.py`, CLI/TUI modules, etc.) must NEVER import from, depend on, or require files in `Julius_Test/`.
   - The application must remain 100% operational, fully functional, and error-free even if the `Julius_Test/` folder is deleted at any time.

3. **Production Code Placement**:
   - Production code and bugfixes must ALWAYS be committed directly to the main codebase (`src/`).
   - Only test programs and test fixtures belong in `Julius_Test/`.
