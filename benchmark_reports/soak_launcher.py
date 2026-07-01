"""Launcher for soak benchmark — writes output line-by-line to log file."""
import subprocess
import sys

log = open(
    r"C:\Users\peter\Desktop\jarvis\benchmark_reports\soak_2h_stdout.txt",
    "w",
    buffering=1,
)
proc = subprocess.Popen(
    [
        sys.executable,
        "-u",
        "benchmarks/soak_benchmark.py",
        "--duration",
        "7200",
        "--report",
        r"C:\Users\peter\Desktop\jarvis\benchmark_reports\soak_2h_report.json",
    ],
    cwd=r"C:\Users\peter\Desktop\jarvis",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
with open(
    r"C:\Users\peter\Desktop\jarvis\benchmark_reports\soak_pid.txt", "w"
) as f:
    f.write(str(proc.pid))
print(f"Soak PID: {proc.pid}", flush=True)

while True:
    line = proc.stdout.readline()
    if not line and proc.poll() is not None:
        break
    if line:
        log.write(line.decode("utf-8", errors="replace"))
        log.flush()
proc.wait()
log.close()
print(f"Soak exited with code {proc.returncode}", flush=True)
