@echo off
echo Starting NAVISCAPE Backend...
start cmd /k "cd backend && if not exist venv (python -m venv venv) && venv\Scripts\activate && pip install -r requirements.txt && python run.py"

echo Starting NAVISCAPE Frontend...
start cmd /k "cd frontend && npm run dev"

echo Both servers are starting in separate windows!
