Comprehensive Refactoring & Chunking Architecture Plan
To eliminate file bloat, context window overload, and editing regressions, we will break down the application into a Clean, Modular, Component-Based Architecture.

Instead of having monolithic bundles or massive mixed files, every view, UI atom, state manager, and script will exist in its own dedicated, single-responsibility file.

Proposed Target Folder Structure
Plaintext
frontend/
├── public/                     # Static public assets
│   ├── favicon.svg
│   └── fonts/                  # Self-hosted web fonts
├── src/
│   ├── assets/                 # Shared images and static assets
│   ├── components/             # Reusable UI Atoms & Molecules
│   │   ├── common/
│   │   │   ├── GlowingLogo.jsx     # Animated logo/brand component
│   │   │   ├── ToggleSwitch.jsx    # Generic toggle switch
│   │   │   ├── CodeBlock.jsx       # Syntax highlighted code block + copy
│   │   │   └── MessageBubble.jsx   # Individual message bubble component
│   │   ├── layout/
│   │   │   ├── Sidebar.jsx         # Navigation sidebar + profile menu
│   │   │   └── Header.jsx          # Active task title & status bar
│   │   ├── chat/
│   │   │   ├── PromptInputBox.jsx  # Main composer / text input + attachments
│   │   │   └── ThinkingPanel.jsx   # Accordion trace / reasoning visualizer
│   ├── views/                  # Standalone Main Page Views
│   │   ├── HomeView.jsx            # Welcome screen + quick start prompts
│   │   ├── TaskView.jsx            # Active agent execution & chat stream
│   │   ├── HistoryView.jsx         # Past conversation logs & cards
│   │   ├── ProjectsView.jsx        # Project workspaces & task assignment
│   │   ├── AutomationView.jsx      # Scheduled workflows & triggers
│   │   ├── PluginsView.jsx         # Tool integrations & connectors
│   │   └── SettingsView.jsx        # System settings & provider configs
│   ├── hooks/                  # Isolated Custom React Hooks
│   │   ├── useWebSocket.js         # Real-time WebSocket connection engine
│   │   ├── useSpeechToText.js      # Browser STT / Voice recognition hook
│   │   ├── useAudioPlayback.js     # TTS preview & sound effect engine
│   │   └── useLocalStorage.js      # Persistent state manager
│   ├── styles/
│   │   ├── index.css               # Tailwind & font definitions
│   │   └── themes.js               # Color tokens & theme palette constants
│   ├── App.jsx                 # Minimal Root Router (~60 lines)
│   └── main.jsx                # Application DOM entry point
├── package.json
└── vite.config.js
Step-by-Step Implementation Task List
Here is the exact sequential execution order. We will execute these tasks one file at a time so that each piece is verified before moving to the next.

Phase 1: Foundations & Utilities
[ ] Task 1.1: Extract Theme Tokens (src/styles/themes.js)

Purpose: Move light/dark color definitions, glow effects, and brand constants out of UI components into a centralized theme configuration.

[ ] Task 1.2: Extract Atomic UI Components (src/components/common/ToggleSwitch.jsx, src/components/common/GlowingLogo.jsx)

Purpose: Isolate independent visual elements so they can be imported anywhere without duplication.

Phase 2: Custom Hooks (Logic Isolation)
[ ] Task 2.1: Extract WebSocket Communication Hook (src/hooks/useWebSocket.js)

Purpose: Encapsulate socket lifecycle, task streaming events (step_start, thought, action, done), and reconnection logic.

[ ] Task 2.2: Extract Voice & Audio Hook (src/hooks/useSpeechToText.js)

Purpose: Isolate SpeechRecognition API calls and microphone toggle states.

Phase 3: Core Navigation & Layout
[ ] Task 3.1: Extract Sidebar Navigation (src/components/layout/Sidebar.jsx)

Purpose: Separate navigation routes, hover behaviors, and theme toggling into a dedicated sidebar file.

[ ] Task 3.2: Extract Header Bar (src/components/layout/Header.jsx)

Purpose: Handle task titles, short title truncation, and back navigation.

Phase 4: Chat Sub-Components
[ ] Task 4.1: Extract Prompt Composer (src/components/chat/PromptInputBox.jsx)

Purpose: Manage textarea auto-resizing, file attachments, and submission controls in a dedicated file.

[ ] Task 4.2: Extract Thinking Trace Panel (src/components/chat/ThinkingPanel.jsx)

Purpose: Isolate the step-by-step reasoning accordion and command trace display.

[ ] Task 4.3: Extract Code Block & Copy Manager (src/components/common/CodeBlock.jsx)

Purpose: Handle markdown code block rendering, language badges, and clipboard feedback.

Phase 5: Main Dashboard Views
[ ] Task 5.1: Extract Home / Landing View (src/views/HomeView.jsx)

Purpose: Render the initial hero section, animated logo, and primary composer box.

[ ] Task 5.2: Extract Active Task / Chat View (src/views/TaskView.jsx)

Purpose: Orchestrate message history rendering, live thinking traces, confirmation popups, and follow-up inputs.

[ ] Task 5.3: Extract History View (src/views/HistoryView.jsx)

Purpose: Manage past conversation cards, project tagging, and deletion features.

[ ] Task 5.4: Extract Projects View (src/views/ProjectsView.jsx)

Purpose: Render workspace project cards, search, and creation forms.

[ ] Task 5.5: Extract Automation View (src/views/AutomationView.jsx)

Purpose: Display scheduled workflows, triggers, and active toggles.

[ ] Task 5.6: Extract Plugins & Integrations View (src/views/PluginsView.jsx)

Purpose: Render third-party tool cards, authentication statuses, and connect buttons.

[ ] Task 5.7: Extract Settings Panel (src/views/SettingsView.jsx)

Purpose: Manage tabbed configurations (Agent, Model, Voice, Memory, Tools, Appearance, Privacy).

Phase 6: Root Integration & Verification
[ ] Task 6.1: Refactor Main Router (src/App.jsx)

Purpose: Import all extracted view components and pass props down cleanly.

[ ] Task 6.2: Build & Integration Check

Purpose: Run the build step to confirm zero syntax errors, broken imports, or missing dependencies.