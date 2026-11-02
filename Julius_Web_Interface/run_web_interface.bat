@echo off
title Julius Universal Web Interface
echo ========================================================
echo Launching Julius Universal Web Interface...
echo Interconnected: Desktop, Apple iOS, Android APK, Julius Apps
echo ========================================================
cd /d "%~dp0"
python server.py --open
pause

