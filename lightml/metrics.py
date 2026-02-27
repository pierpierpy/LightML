from pathlib import Path
import sqlite3


import sqlite3

def add_metric(
    db: str,
    family: str,
    metric_name: str,
    value: float,
    model_name: str | None = None,
    checkpoint_id: int | None = None,
) -> int:
    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            # Validazione logica (prima del DB)
            if (model_name is None and checkpoint_id is None) or \
               (model_name is not None and checkpoint_id is not None):
                return 0

            model_id = None

            if model_name is not None:
                row = conn.execute(
                    "SELECT id FROM model WHERE model_name = ?;",
                    (model_name,),
                ).fetchone()

                model_id = row[0] if row else -1

            conn.execute(
                """
                INSERT INTO metrics (model_id, checkpoint_id, family, metric_name, value)
                VALUES (?, ?, ?, ?, ?);
                """,
                (model_id, checkpoint_id, family, metric_name, value),
            )

            conn.commit()

        return 1

    except Exception as e:
        print("ERROR:", e)
        raise