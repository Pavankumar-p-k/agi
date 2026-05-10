"""
main.py — JARVIS Social AI — Master Boot
=========================================
Boots all modules in order. Single entry point.

Usage:
    python main.py              # start full system
    python main.py --dashboard  # dashboard only
    python main.py --test       # run test suite
    python main.py --setup      # first-time setup wizard
"""
from __future__ import annotations
import argparse, asyncio, logging, os, sys, time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jarvis.main")

DB_PATH = os.environ.get("JARVIS_DB", "jarvis_social.db")


async def boot() -> None:
    print("""
╔══════════════════════════════════════════════════╗
║         J A R V I S   S O C I A L   A I         ║
║         Transparent AI Social Assistant          ║
╚══════════════════════════════════════════════════╝
""")

    # ── Step 1: Database ────────────────────────────────────────
    from db.schema import init_db, set_setting
    init_db(DB_PATH)
    set_setting("laptop_status", "online", DB_PATH)
    logger.info("[Boot] Database ✓")

    # ── Step 2: Friend Registry ─────────────────────────────────
    from friends.registry import FriendRegistry
    registry = FriendRegistry(DB_PATH)
    friends = registry.all_friends()
    logger.info("[Boot] Friend Registry ✓  (%d friends)", len(friends))

    # ── Step 3: Brain Router ────────────────────────────────────
    from brain.router import BrainRouter
    router = BrainRouter()
    logger.info("[Boot] Brain Router ✓")

    # ── Step 4: Auto Reply Engine ───────────────────────────────
    from reply.auto_reply import AutoReplyEngine
    reply_engine = AutoReplyEngine(db_path=DB_PATH)
    logger.info("[Boot] Auto Reply Engine ✓")

    # ── Step 5: Shadow Learner ──────────────────────────────────
    from brain.learning import ShadowLearner
    learner = ShadowLearner(db_path=DB_PATH)
    logger.info("[Boot] Shadow Learner ✓")

    # ── Step 6: Experiment Engine ───────────────────────────────
    from experiments.engine import ExperimentEngine, InterventionEngine
    exp_engine = ExperimentEngine(db_path=DB_PATH)
    iv_engine  = InterventionEngine(db_path=DB_PATH,
                                     notify_fn=lambda iv: logger.warning(
                                         "[INTERVENTION HIGH] %s — %s", iv.friend_id, iv.trigger_reason))
    logger.info("[Boot] Experiment + Intervention Engines ✓")

    # ── Step 7: Memory Cleanup ──────────────────────────────────
    from jarvis_os.memory.memory_manager import MemoryManager
    cleanup = MemoryCleanup(db_path=DB_PATH)
    logger.info("[Boot] Memory Cleanup ✓")

    # ── Step 8: Social Presence Engine ─────────────────────────
    from reply.presence import SocialPresenceEngine
    presence = SocialPresenceEngine(db_path=DB_PATH)
    logger.info("[Boot] Presence Engine ✓")

    print("\n[JARVIS] All systems online. Running...\n")

    # ── Background tasks ────────────────────────────────────────
    async def daily_maintenance():
        while True:
            await asyncio.sleep(86400)   # every 24h
            logger.info("[Maintenance] Running daily cleanup...")
            stats = cleanup.run_daily_cleanup()
            logger.info("[Maintenance] Cleanup done: %s", stats)

    async def periodic_intervention_check():
        while True:
            await asyncio.sleep(3600)   # every hour
            friends_list = registry.all_friends()
            for f in friends_list:
                iv = iv_engine.check(f.friend_id)
                if iv:
                    logger.info("[Intervention] %s — %s severity %s",
                                 f.display_name, iv.trigger_reason, iv.severity)

    async def run_dashboard():
        from dashboard.admin import run_dashboard as _run
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run, DB_PATH)

    await asyncio.gather(
        presence.start(),
        daily_maintenance(),
        periodic_intervention_check(),
        run_dashboard(),
        return_exceptions=True,
    )


def setup_wizard() -> None:
    """First-time setup: configure friends."""
    print("\n=== JARVIS Social AI — First Time Setup ===\n")
    print("Edit friends/registry.py and fill in SPECIAL_FRIENDS config.")
    print("Then run: python main.py\n")
    print("SPECIAL_FRIENDS template:")
    print("""  {
    "name": "Your Friend's Name",
    "phone": "+91XXXXXXXXXX",
    "instagram_id": "their_username",
    "nickname": "nickname",
    "platform": "whatsapp",
    "base_traits": {
        "humor": 0.7, "caring": 0.85,
        "emoji": 0.75, "energy": 0.7
    }
  }""")


def run_tests() -> None:
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_all.py", "-v", "--tb=short"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Social AI")
    parser.add_argument("--dashboard", action="store_true", help="Dashboard only")
    parser.add_argument("--test",      action="store_true", help="Run test suite")
    parser.add_argument("--setup",     action="store_true", help="Setup wizard")
    args = parser.parse_args()

    if args.test:
        run_tests()
    elif args.setup:
        setup_wizard()
    else:
        asyncio.run(boot())
