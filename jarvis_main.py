from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    from core.config import HOST, PORT
    import uvicorn

    print(f"\n[JARVIS] Server starting at http://{HOST}:{PORT}")
    print(f"[JARVIS] API docs at  http://localhost:{PORT}/docs\n")
    uvicorn.run("core.main:app", host=HOST, port=PORT, reload=True, log_level="info")


if __name__ == "__main__":
    main()
