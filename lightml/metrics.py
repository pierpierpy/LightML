import sqlite3


def add_metric(
    db: str,
    family: str,
    metric_name: str,
    value: float,
    model_name: str | None = None,
    checkpoint_id: int | None = None,
    run_name: str | None = None,
) -> int:

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            # ------------------------
            # Validazione input
            # ------------------------
            if (model_name is None and checkpoint_id is None) or \
               (model_name is not None and checkpoint_id is not None):
                raise ValueError("Specify either model_name or checkpoint_id")

            model_id = None

            # ------------------------
            # MODEL METRIC (run scoped)
            # ------------------------
            if model_name is not None:

                if run_name is None:
                    raise ValueError("run_name is required when logging model metric")

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
            # INSERT METRIC
            # ------------------------
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