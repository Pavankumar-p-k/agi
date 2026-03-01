from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

HOST = "0.0.0.0"
PORT = 9001
DB_FILE = Path("data/call_records_pc.db")


def init_db() -> None:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_FILE)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS call_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_name TEXT,
            platform TEXT,
            transcript TEXT,
            timestamp INTEGER,
            important INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )
    con.commit()
    con.close()


def save_record(record: dict) -> int:
    con = sqlite3.connect(DB_FILE)
    cur = con.execute(
        """
        INSERT INTO call_records (caller_name, platform, transcript, timestamp, important, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("caller_name", "Unknown"),
            record.get("platform", "SIM"),
            record.get("transcript", ""),
            int(record.get("timestamp", int(time.time() * 1000))),
            1 if record.get("important") else 0,
            datetime.now().isoformat(),
        ),
    )
    con.commit()
    row_id = int(cur.lastrowid)
    con.close()
    return row_id


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    try:
        payload = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            payload += chunk
        if not payload:
            return

        data = json.loads(payload.decode("utf-8").strip())
        if data.get("type") == "call_record":
            row_id = save_record(data)
            conn.sendall(json.dumps({"status": "ok", "id": row_id}).encode("utf-8"))
    except Exception:
        try:
            conn.sendall(json.dumps({"status": "error"}).encode("utf-8"))
        except Exception:
            pass
    finally:
        conn.close()


def run_server() -> None:
    init_db()
    print(f"[CallSync] Listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(8)
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()


if __name__ == "__main__":
    run_server()
