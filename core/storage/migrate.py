from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.storage.registry import SYSTEM_DB, ensure_db_dir

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
        tgt_table_names = {r["name"] for r in tgt_tables}

        to_copy = [t for t in (tables or src_table_names) if t in src_table_names]
        if not to_copy:
            logger.info("No tables to copy from %s to %s", source_db, target_db)
            return result

        for table in to_copy:
            # Get schema
            schema_rows = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchall()
            if not schema_rows or not schema_rows[0]["sql"]:
                continue
            create_sql = schema_rows[0]["sql"]

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
                    tgt.execute(idx["sql"])
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


def run_all() -> dict[str, dict[str, int]]:
    """Run all storage migrations. Returns per-source results."""
    results: dict[str, dict[str, int]] = {}
    results["workflow"] = merge_workflow_db_to_system()
    results["brain"] = merge_brain_db_to_system()
    return results
