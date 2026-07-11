from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.storage.registry import APP_DB, HOME_DIR, SYSTEM_DB, USER_DB, ensure_db_dir

logger = logging.getLogger(__name__)


def copy_tables(source_db: str, target_db: str, tables: list[str] | None = None) -> dict[str, int]:
    """Copy tables from source DB to target DB.

    Args:
        source_db: Path to the source database.
        target_db: Path to the target database.
        tables: Specific table names to copy. If None, copies all user tables.

    Returns:
        Dict mapping table name → row count copied.
    """
    if not Path(source_db).exists():
        logger.warning("Source DB not found: %s", source_db)
        return {}

    ensure_db_dir(target_db)
    result: dict[str, int] = {}

    with sqlite3.connect(source_db) as src, sqlite3.connect(target_db) as tgt:
        src.row_factory = sqlite3.Row

        # Get all user tables from source
        src_tables = src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        src_table_names = {r["name"] for r in src_tables}

        # Get existing tables in target
        tgt_tables = tgt.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        tgt_table_names = {r[0] for r in tgt_tables}

        to_copy = [t for t in (tables or src_table_names) if t in src_table_names]
        if not to_copy:
            logger.info("No tables to copy from %s to %s", source_db, target_db)
            return result

        for table in to_copy:
            # Get schema
            schema_rows = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchall()
            if not schema_rows or not schema_rows[0][0]:
                continue
            create_sql = schema_rows[0][0]

            # Create table in target if it doesn't exist
            if table not in tgt_table_names:
                tgt.execute(create_sql)

            # Copy data
            rows = src.execute(f"SELECT * FROM [{table}]").fetchall()
            if not rows:
                continue

            columns = [desc[0] for desc in src.execute(f"SELECT * FROM [{table}] LIMIT 0").description]
            placeholders = ",".join("?" for _ in columns)
            col_names = ",".join(f"[{c}]" for c in columns)

            inserted = 0
            for row in rows:
                values = [row[c] for c in columns]
                try:
                    tgt.execute(
                        f"INSERT OR IGNORE INTO [{table}] ({col_names}) VALUES ({placeholders})",
                        values,
                    )
                    inserted += 1
                except Exception as e:
                    logger.debug("Skipping row in %s: %s", table, e)

            # Create indexes from source
            idx_rows = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                (table,),
            ).fetchall()
            for idx in idx_rows:
                try:
                    tgt.execute(idx[0])
                except Exception:
                    pass

            tgt.commit()
            result[table] = inserted
            logger.info("Copied %d rows to %s.%s", inserted, Path(target_db).name, table)

    return result


def merge_workflow_db_to_system() -> dict[str, int]:
    """Migrate all tables from legacy workflow.db to system.db."""
    from core.storage.registry import LEGACY_WORKFLOW_DB

    return copy_tables(LEGACY_WORKFLOW_DB, SYSTEM_DB)


def merge_brain_db_to_system() -> dict[str, int]:
    """Migrate all non-memory tables from brain.db to system.db."""
    from core.storage.registry import LEGACY_BRAIN_DB

    return copy_tables(LEGACY_BRAIN_DB, SYSTEM_DB)


def merge_goals_db_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_GOALS_DB
    return copy_tables(LEGACY_GOALS_DB, SYSTEM_DB)


def merge_jarvis_memory_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_JARVIS_MEMORY_DB
    return copy_tables(LEGACY_JARVIS_MEMORY_DB, SYSTEM_DB)


def merge_browser_facts_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_BROWSER_FACTS_DB
    return copy_tables(LEGACY_BROWSER_FACTS_DB, SYSTEM_DB)


def merge_inbox_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_INBOX_DB
    return copy_tables(LEGACY_INBOX_DB, SYSTEM_DB)


def merge_benchmark_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_BENCHMARK_DB
    return copy_tables(LEGACY_BENCHMARK_DB, SYSTEM_DB)


def merge_training_log_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_TRAINING_LOG_DB
    return copy_tables(LEGACY_TRAINING_LOG_DB, SYSTEM_DB)


def merge_failure_memory_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_FAILURE_MEMORY_DB
    return copy_tables(LEGACY_FAILURE_MEMORY_DB, SYSTEM_DB)


def merge_plugin_state_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_PLUGIN_STATE_DB
    return copy_tables(LEGACY_PLUGIN_STATE_DB, SYSTEM_DB)


def merge_plugin_secrets_to_system() -> dict[str, int]:
    from core.storage.registry import LEGACY_PLUGIN_SECRETS_DB
    return copy_tables(LEGACY_PLUGIN_SECRETS_DB, SYSTEM_DB)


def merge_user_subdbs_to_user_db() -> dict[str, int]:
    from core.storage.registry import USER_DB, HOME_DIR
    results: dict[str, int] = {}
    legacy_dbs = [
        "agent_state.db", "agent_checkpoints.db", "cron.db",
        "commitments.db", "constitutional_memory.db", "feedback.db",
        "benchmark.db", "orchestration.db", "workflow_learning.db",
    ]
    for name in legacy_dbs:
        path = str(HOME_DIR / name)
        table_results = copy_tables(path, USER_DB)
        results.update(table_results)
    return results


def merge_jarvis_db_to_app_db() -> dict[str, int]:
    from core.storage.registry import LEGACY_JARVIS_DB
    return copy_tables(LEGACY_JARVIS_DB, APP_DB)


LEGACY_DB_PATHS = [
    "workflow.db", "brain.db", "goals.db", "jarvis_memory.db",
    "browser_facts.db", "inbox.db", "benchmark.db", "training_log.db",
    "failure_memory.db", "plugin_state.db", "plugin_secrets.db", "jarvis.db",
]

LEGACY_JSON_PATHS = [
    "data/knobs.json",
    "data/research_reflections.json",
    "data/health.json",
    "data/learnings.json",
]


def delete_legacy_dbs(dry_run: bool = True) -> list[str]:
    """Delete legacy database files after successful migration.

    Args:
        dry_run: If True, only report which files would be deleted.

    Returns:
        List of deleted (or would-be-deleted) file paths.
    """
    from core.storage.registry import DATA_DIR, HOME_DIR

    deleted: list[str] = []

    for name in LEGACY_DB_PATHS:
        path = DATA_DIR / name
        if path.exists():
            if dry_run:
                logger.info("[DRY RUN] Would delete legacy DB: %s", path)
            else:
                path.unlink()
                logger.info("Deleted legacy DB: %s", path)
            deleted.append(str(path))

    for name in LEGACY_JSON_PATHS:
        path = Path(name)
        if not path.is_absolute():
            path = DATA_DIR / name if not name.startswith("data/") else Path(name)
        if path.exists():
            if dry_run:
                logger.info("[DRY RUN] Would delete legacy JSON: %s", path)
            else:
                path.unlink()
                logger.info("Deleted legacy JSON: %s", path)
            deleted.append(str(path))

    return deleted


def run_all(delete_legacy: bool = False) -> dict[str, dict[str, int]]:
    """Run all storage migrations. Returns per-source results.

    Args:
        delete_legacy: If True, delete legacy DB files after successful migration.
    """
    results: dict[str, dict[str, int]] = {}
    results["workflow"] = merge_workflow_db_to_system()
    results["brain"] = merge_brain_db_to_system()
    results["goals"] = merge_goals_db_to_system()
    results["jarvis_memory"] = merge_jarvis_memory_to_system()
    results["browser_facts"] = merge_browser_facts_to_system()
    results["inbox"] = merge_inbox_to_system()
    results["benchmark"] = merge_benchmark_to_system()
    results["training_log"] = merge_training_log_to_system()
    results["failure_memory"] = merge_failure_memory_to_system()
    results["plugin_state"] = merge_plugin_state_to_system()
    results["plugin_secrets"] = merge_plugin_secrets_to_system()

    if delete_legacy:
        deleted = delete_legacy_dbs(dry_run=False)
        results["_deleted_legacy"] = {"files": len(deleted)}

    return results
