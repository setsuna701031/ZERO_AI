@echo off
echo ============================
echo Starting WSL Ollama...
echo ============================

wsl -d Ubuntu -e bash -c "~/start_ollama.sh"

timeout /t 5

echo ============================
echo Starting ZERO AI...
echo ============================

set OLLAMA_BASE_URL=http://127.0.0.1:11434
set OLLAMA_MODEL=zero_general:latest

cd /d E:\zero_ai
python app.py

pause