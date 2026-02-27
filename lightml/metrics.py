from pathlib import Path
import sqlite3


def add_metric(
    db_path: str,
    model_name: str,
    family: str,
    metric_name: str,
    value: float,
) -> int:
    try:
        db_path = Path(db_path).resolve()

        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            # get model_id
            row = conn.execute(
                "SELECT id FROM model WHERE model_name = ?;",
                (model_name,),
            ).fetchone()

            if row is None:
                return 0

            model_id = row[0]

            # insert metric
            conn.execute(
                """
                INSERT INTO metrics (model_id, family, metric_name, value)
                VALUES (?, ?, ?, ?);
                """,
                (model_id, family, metric_name, value),
            )

            conn.commit()

        return 1

    except Exception:
        return 0