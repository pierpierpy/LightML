from datetime import datetime
import sqlite3


def register_checkpoint(db: str,
                        run_name: str,
                        model_name: str,
                        step: int,
                        path: str) -> int:

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

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
            # INSERT CHECKPOINT
            # ------------------------
            cursor = conn.execute(
                """
                INSERT INTO checkpoint (model_id, step, path, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (model_id, step, path, datetime.utcnow().isoformat()),
            )

            checkpoint_id = cursor.lastrowid
            conn.commit()

            return checkpoint_id

    except Exception as e:
        print("ERROR:", e)
        raise