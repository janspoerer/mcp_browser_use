@echo off
set PYTHONPATH=C:\Users\j.spoerer\code\scraping\mcp_browser_use\src
set CHROME_PROFILE_NAME=Profile 15
set CHROME_EXECUTABLE_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
set CHROME_PROFILE_USER_DATA_DIR=C:\Users\j.spoerer\AppData\Local\Google\Chrome\User Data
set CHROME_REMOTE_DEBUG_PORT=9225
set MCP_HEADLESS=0
set MAX_SNAPSHOT_CHARS=10000

cd /d C:\Users\j.spoerer\code\scraping\mcp_browser_use
"C:\Users\j.spoerer\code\scraping\mcp_browser_use\.venv\Scripts\python.exe" -m mcp_browser_use
