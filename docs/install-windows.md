# Installing Julius on Windows (Native)

Julius runs natively on **Windows 10 and Windows 11** using PowerShell or Command Prompt — no WSL or virtual machine is required.

---

## 1. Prerequisites

- **Python 3.10+**: Download from [python.org](https://www.python.org/downloads/) or install via winget:
  ```powershell
  winget install Python.Python.3.12
  ```
  > **Important:** Check "Add python.exe to PATH" during installation.
- **Windows Terminal** (recommended for best TUI unicode and color rendering).

---

## 2. Installation (PowerShell)

Open PowerShell in the project directory:

```powershell
# Run the PowerShell installer
.\install.ps1

# Optional flags:
.\install.ps1 -NoBrowser   # Skip Playwright browser download
.\install.ps1 -NoVerify    # Skip post-install verification
```

Alternatively, you can run the universal Python installer:
```powershell
python install.py
```

---

## 3. Running Julius

### Interactive CLI / Terminal UI
```powershell
# PowerShell:
.\julius.ps1

# Or from CMD:
julius.cmd

# Or using universal launcher:
python julius.py
```

### Direct TUI Mode
```powershell
.\start_tui.ps1
```

### Web GUI Server
```powershell
.\.venv\Scripts\python.exe julius_gui.py
```

---

## 4. Troubleshooting

- **Execution Policy Error:** If PowerShell blocks script execution:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```
  Or run with bypass:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```
- **PortAudio / Audio:** Wheels for `sounddevice` bundle PortAudio on Windows automatically.
- **Clipboard:** Native `clip.exe` is used; clipboard copy works out of the box.
