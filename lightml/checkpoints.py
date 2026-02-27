from datetime import datetime
import sqlite3

def register_checkpoint(db: str, model_name: str, step: int, path: str) -> int:
    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            row = conn.execute(
                "SELECT id FROM model WHERE model_name = ?;",
                (model_name,),
            ).fetchone()

            model_id = row[0] if row else -1

            conn.execute(
                """
                INSERT INTO checkpoint (model_id, step, path, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (model_id, step, path, datetime.utcnow().isoformat()),
            )

            conn.commit()

        return 1

    except Exception as e:
        print("ERROR:", e)
        raise