@echo off
cd /d "%~dp0"
py scripts\build_release.py
:finish
pause
