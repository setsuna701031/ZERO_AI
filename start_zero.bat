@echo off
echo ==============================
echo Starting Ollama (WSL)...
echo ==============================

wsl -d Ubuntu -e bash -c "ollama serve &"

timeout /t 5

echo ==============================
echo Starting ZERO Pipeline...
echo ==============================

set OLLAMA_BASE_URL=http://127.0.0.1:11434
set OLLAMA_MODEL=zero_general:latest

cd /d E:\zero_ai
python run_zero.py

pause