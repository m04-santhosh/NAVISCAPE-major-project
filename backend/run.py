"""
NAVISCAPE Backend Runner
Start the FastAPI server with uvicorn.
"""

import os
import sys

# Ensure the project root (parent of backend/) is on the Python path
# so that the `app` package can be found by uvicorn's subprocess.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[os.path.join(PROJECT_ROOT, "backend", "app")],
        log_level="info",
    )
