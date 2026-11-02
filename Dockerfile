# Use an official Python runtime as a parent image
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    QT_DEBUG_PLUGINS=1

WORKDIR /app

# Install system dependencies required for PyQt6, Playwright, and audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PyQt6 dependencies
    libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
    libxcb-keysyms1 libxcb-shape0 libdbus-1-3 libx11-xcb1 \
    libfontconfig1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    # X11 dependencies for GUI
    libxcomposite1 libxcursor1 libxdamage1 libxrandr2 libxtst6 \
    # Sounddevice / Audio dependencies
    libportaudio2 libasound2-dev \
    # Playwright dependencies
    curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser dependencies and chromium
RUN playwright install-deps && playwright install chromium

# Copy the application code
COPY . .

# Run the GUI application
CMD ["python3", "julius_gui.py"]
