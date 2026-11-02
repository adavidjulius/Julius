# Installing Julius on macOS

Julius is fully optimized for **macOS (Apple Silicon & Intel)**.

---

## 1. Prerequisites

- **Python 3.10+**: Install via Homebrew:
  ```bash
  brew install python@3.12
  ```
- **Command Line Tools** (for compiled extensions):
  ```bash
  xcode-select --install
  ```

---

## 2. Installation

```bash
# Run the installer
./install.sh

# Optional flags:
./install.sh --no-browser   # Skip Playwright browser download
./install.sh --no-verify    # Skip verification
```

Alternatively, run the universal Python installer:
```bash
python3 install.py
```

---

## 3. Running Julius

### Interactive CLI / Terminal UI
```bash
./julius
```

### Julius Minimalist TUI
```bash
./start_tui.sh
```

### Web GUI Server
```bash
./.venv/bin/python julius_gui.py
# Or daemon:
./.venv/bin/python juliusd.py
```
