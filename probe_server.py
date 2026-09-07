import faulthandler, sys, os

faulthandler.dump_traceback_later(40, exit=False, file=sys.stderr)
sys.stderr.write("FAULTHANDLER: will dump stack in 40s\n")
sys.stderr.flush()

os.environ["PYTHONPATH"] = r"C:\Users\peter\Desktop\jarvis"
sys.path.insert(0, r"C:\Users\peter\Desktop\jarvis")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("core.main:app", host="127.0.0.1", port=8000, log_level="warning")
