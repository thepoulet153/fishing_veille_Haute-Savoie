@echo off
chcp 65001 > nul
cd /d "%~dp0"
py collect.py
start http://localhost:8000
py -m http.server 8000
