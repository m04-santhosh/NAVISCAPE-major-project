@echo off
echo Starting NAVISCAPE Backend...
start cmd /k "cd backend && python -m venv venv && venv\Scripts\activate && python run.py"

echo Starting NAVISCAPE Frontend...
start cmd /k "cd frontend && npx vite"

echo Both servers are starting in separate windows!
