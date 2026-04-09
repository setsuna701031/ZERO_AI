@echo off
title ZERO Local Web Search

cd /d E:\zero_ai

set WEB_SEARCH_MODE=searxng
set SEARXNG_BASE_URL=http://127.0.0.1:8888
set WEB_SEARCH_FALLBACK_TO_MOCK=true

echo ========================================
echo ZERO Local Web Search Starting...
echo Project Path: E:\zero_ai
echo WEB_SEARCH_MODE=%WEB_SEARCH_MODE%
echo SEARXNG_BASE_URL=%SEARXNG_BASE_URL%
echo WEB_SEARCH_FALLBACK_TO_MOCK=%WEB_SEARCH_FALLBACK_TO_MOCK%
echo ========================================
echo.

python app.py

pause