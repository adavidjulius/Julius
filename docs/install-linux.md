# Installing Julius on Linux (Ubuntu, Debian, Fedora, Arch, WSL)

Julius runs natively on standard Linux distributions as well as WSL.

---

## 1. Prerequisites

### Ubuntu / Debian:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip libportaudio2 xclip
```

### Fedora / RHEL:
```bash
sudo dnf install -y python3 python3-pip portaudio xclip
```

### Arch Linux:
```bash
sudo pacman -S python python-pip portaudio xclip
```

---

## 2. Installation

```bash
# Run the installer
./install.sh

# Optional flags:
./install.sh --no-browser
./install.sh --no-verify
```

Or universal installer:
```bash
python3 install.py
```

---

## 3. Running Julius

### CLI / TUI
```bash
./julius
```

### Web GUI Server
```bash
./.venv/bin/python julius_gui.py
```
