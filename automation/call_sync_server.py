# backend/call_server/call_sync_server.py
#
# JARVIS Windows Call Sync Server
# ─────────────────────────────────────────────
# Listens for call records from Android via TCP socket
# Saves to local DB, displays desktop notification,
# optionally plays TTS summary

import socket, json, threading, sqlite3, time, os
from datetime import datetime
from pathlib import Path

try:
    import plyer; _has_notif = True
except: _has_notif = False

try:
    import pyttsx3
    _tts = pyttsx3.init()
    _tts.setProperty('rate', 160)
    _has_tts = True
except: _has_tts = False


PORT     = 9001
DB_FILE  = "data/call_records_pc.db"
HOST     = "0.0.0.0"

Path("data").mkdir(exist_ok=True)


# ── Database ─────────────────────────────────────────────

def init_db():
    con = sqlite3.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS call_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_name TEXT,
            platform    TEXT,
            transcript  TEXT,
            timestamp   INTEGER,
            important   INTEGER DEFAULT 0,
            notified    INTEGER DEFAULT 0,
            created_at  TEXT
        )
    """)
    con.commit()
    con.close()

def save_record(data: dict) -> int:
    con = sqlite3.connect(DB_FILE)
    cur = con.execute(
        "INSERT INTO call_records (caller_name, platform, transcript, timestamp, important, created_at) VALUES (?,?,?,?,?,?)",
        (data.get("caller_name","Unknown"),
         data.get("platform","SIM"),
         data.get("transcript",""),
         data.get("timestamp", int(time.time()*1000)),
         1 if data.get("important") else 0,
         datetime.now().isoformat())
    )
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid

def get_unread_important():
    con = sqlite3.connect(DB_FILE)
    rows = con.execute(
        "SELECT * FROM call_records WHERE important=1 AND notified=0 ORDER BY timestamp DESC"
    ).fetchall()
    con.close()
    return rows


# ── Notification + TTS ──────────────────────────────────

def notify_desktop(caller: str, platform: str, transcript: str, important: bool):
    title = "JARVIS - IMPORTANT" if important else "JARVIS - Missed Call"
    msg   = f"{platform} | {caller}\n{transcript[:100]}" if transcript else f"{platform} | {caller}"

    if _has_notif:
        try:
            plyer.notification.notify(
                title=title, message=msg,
                app_name="JARVIS", timeout=10)
        except Exception as e:
            print(f"[Notif] {e}")

    if _has_tts and important:
        try:
            speech = f"Important message from {caller} via {platform}. {transcript[:80]}"
            _tts.say(speech)
            _tts.runAndWait()
        except Exception as e:
            print(f"[TTS] {e}")


# ── TCP Server ───────────────────────────────────────────

def handle_client(conn, addr):
    print(f"[Server] Connected: {addr}")
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk: break
            data += chunk

        if data:
            record = json.loads(data.decode("utf-8").strip())
            print(f"[Server] Received: {record}")

            if record.get("type") == "call_record":
                rid = save_record(record)
                print(f"[Server] Saved record #{rid}")

                # Desktop notification
                notify_desktop(
                    record.get("caller_name","Unknown"),
                    record.get("platform","SIM"),
                    record.get("transcript",""),
                    record.get("important", False)
                )

                # Send ACK
                conn.sendall(json.dumps({"status":"ok","id":rid}).encode())

    except Exception as e:
        print(f"[Server] Error: {e}")
    finally:
        conn.close()


def run_server():
    init_db()
    print(f"[JARVIS Call Sync] Listening on port {PORT}...")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)

        while True:
            try:
                conn, addr = s.accept()
                t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                t.start()
            except KeyboardInterrupt:
                print("\n[Server] Stopped")
                break


# ── Also expose via FastAPI (add to your existing backend) ──

def get_fastapi_router():
    from fastapi import APIRouter
    router = APIRouter(prefix="/api/calls", tags=["calls"])

    @router.get("/")
    def get_all():
        con = sqlite3.connect(DB_FILE)
        rows = con.execute(
            "SELECT * FROM call_records ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
        con.close()
        return [{"id":r[0],"caller_name":r[1],"platform":r[2],
                 "transcript":r[3],"timestamp":r[4],"important":r[5]} for r in rows]

    @router.get("/important")
    def get_important():
        rows = get_unread_important()
        return [{"id":r[0],"caller_name":r[1],"platform":r[2],
                 "transcript":r[3],"timestamp":r[4]} for r in rows]

    return router


if __name__ == "__main__":
    run_server()
