"""Check benchmark database contents."""
import sys, json
sys.path.insert(0, ".")
from core.benchmark.results_store import BenchmarkResultsStore

# Quick query via sqlite3 directly
import sqlite3
conn = sqlite3.connect("data/benchmark.db")
models = conn.execute("SELECT DISTINCT model_id, mode, status, COUNT(*) FROM benchmark_runs GROUP BY model_id, mode, status ORDER BY model_id, mode").fetchall()
for r in models:
    print(f"  {r[0]:20s} {r[1]:20s} {r[2]:10s} count={r[3]}")
total = conn.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
print(f"\n  Total runs: {total}")
conn.close()
