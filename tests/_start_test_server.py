"""Start JARVIS server on port 8002 for testing."""
import sys, os
sys.path.insert(0, r"C:\Users\peter\Desktop\jarvis")

# Override PORT before any imports
import core.config
core.config.PORT = 8002
os.environ["JARVIS_DEV_MODE"] = "true"

import uvicorn
from core.main import app

if __name__ == "__main__":
    print(f"Starting JARVIS on port {core.config.PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=core.config.PORT, log_level="info")
