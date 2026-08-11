@echo off
echo Starting NAVISCAPE Backend...
if exist "backend\venv\Scripts\activate.bat" (
    start cmd /k "cd backend && call venv\Scripts\activate && python run.py"
) else (
    start cmd /k "cd backend && python run.py"
)

echo Starting NAVISCAPE Frontend...
start cmd /k "cd frontend && npm run dev"

echo Both servers are starting in separate windows!
