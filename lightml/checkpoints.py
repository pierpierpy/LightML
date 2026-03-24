from datetime import datetime
import os
import sqlite3
from typing import Optional


def find_checkpoint(
    db: str,
    run_name: str | None = None,
    model_name: str = "",
    step: int = 0,
    path_hint: str | None = None,
) -> Optional[int]:
    """Look up a checkpoint id by model name and step.

    When multiple checkpoints share the same step (e.g. grid-search trials),
    *path_hint* is matched against the stored path to disambiguate.  If no
    *path_hint* is given and there is exactly one match, that id is returned;
    with several matches the first one is returned as a fallback.

    Returns:
        The checkpoint id, or ``None`` if no match is found.
    """
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        if run_name is None:
            run_name = "run_0"

        candidates = conn.execute(
            """
            SELECT c.id, c.path
            FROM checkpoint c
            JOIN model m ON c.model_id = m.id
            JOIN run   r ON m.run_id   = r.id
            WHERE m.model_name = ? AND r.run_name = ? AND c.step = ?
            """,
            (model_name, run_name, step),
        ).fetchall()

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0][0]

        # Disambiguate by path_hint
        if path_hint:
            for cid, cpath in candidates:
                if path_hint in (cpath or ""):
                    return cid

        # Fallback: first match
        return candidates[0][0]


def register_checkpoint(db: str,
                        run_name: str | None = None,
                        model_name: str = "",
                        step: int = 0,
                        path: str = "") -> int:

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            if run_name is None:
                run_name = "run_0"

            # ------------------------
            # GET MODEL ID (run scoped)
            # ------------------------
            row = conn.execute(
                """
                SELECT m.id
                FROM model m
                JOIN run r ON m.run_id = r.id
                WHERE m.model_name = ? AND r.run_name = ?;
                """,
                (model_name, run_name),
            ).fetchone()

            if row is None:
                raise ValueError(
                    f"Model '{model_name}' not found in run '{run_name}'"
                )

            model_id = row[0]

            # ------------------------
            # DEDUP: skip if identical checkpoint already exists
            # ------------------------
            norm_path = os.path.abspath(path)
            existing = conn.execute(
                """
                SELECT id FROM checkpoint
                WHERE model_id = ? AND step = ? AND path = ?;
                """,
                (model_id, step, norm_path),
            ).fetchone()

            if existing:
                return existing[0]

            # ------------------------
            # INSERT CHECKPOINT
            # ------------------------
            cursor = conn.execute(
                """
                INSERT INTO checkpoint (model_id, step, path, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (model_id, step, norm_path, datetime.utcnow().isoformat()),
            )

            checkpoint_id = cursor.lastrowid
            conn.commit()

            return checkpoint_id

    except Exception as e:
        print("ERROR:", e)
        raise