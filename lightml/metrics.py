import sqlite3
import json

# Return codes
METRIC_INSERTED = 1
METRIC_UPDATED  = 2
METRIC_SKIPPED  = 0


def add_metric(
    db: str,
    family: str,
    metric_name: str,
    value: float,
    scores: list[float] | None = None,
    model_name: str | None = None,
    checkpoint_id: int | None = None,
    run_name: str | None = None,
    force: bool = False,
) -> int:
    """
    Log a metric value.

    Deduplication logic:
    - If the exact (model_id/checkpoint_id, family, metric_name) already
      exists in the DB, the metric is **skipped** (returns METRIC_SKIPPED).
    - With ``force=True`` the existing row is **updated** in-place instead
      of inserting a duplicate (returns METRIC_UPDATED).
    - If no duplicate exists, a normal INSERT is performed (returns
      METRIC_INSERTED).
    """

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
            # SCHEMA VALIDATION
            # ------------------------
            schema_count = conn.execute(
                "SELECT COUNT(*) FROM registry_schema"
            ).fetchone()[0]
            
            if schema_count > 0:
                valid_metric = conn.execute(
                    """
                    SELECT COUNT(*) FROM registry_schema 
                    WHERE family = ? AND metric_name = ?
                    """,
                    (family, metric_name),
                ).fetchone()[0]
                
                if valid_metric == 0:
                    raise ValueError(
                        f"Metric (family='{family}', metric_name='{metric_name}') "
                        f"not found in registry schema"
                    )

            # ------------------------
            # DUPLICATE CHECK
            # ------------------------
            if model_id is not None:
                existing = conn.execute(
                    """
                    SELECT id FROM metrics
                    WHERE model_id = ? AND family = ? AND metric_name = ?
                    """,
                    (model_id, family, metric_name),
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT id FROM metrics
                    WHERE checkpoint_id = ? AND family = ? AND metric_name = ?
                    """,
                    (checkpoint_id, family, metric_name),
                ).fetchone()

            if existing:
                if not force:
                    # Already present → skip silently
                    return METRIC_SKIPPED

                # force → update in-place
                conn.execute(
                    "UPDATE metrics SET value = ? WHERE id = ?",
                    (value, existing[0]),
                )
                if scores:
                    metric_id = existing[0]
                    conn.execute(
                    """
                    INSERT OR REPLACE INTO detailed_scores (metric_id, scores, n_samples)
                    VALUES (?, ?, ?);
                    """,
                    (metric_id, json.dumps(scores) , len(scores)),)
                conn.commit()
                return METRIC_UPDATED

            # ------------------------
            # INSERT METRIC
            # ------------------------
            cursor = conn.execute(
                """
                INSERT INTO metrics (model_id, checkpoint_id, family, metric_name, value)
                VALUES (?, ?, ?, ?, ?);
                """,
                (model_id, checkpoint_id, family, metric_name, value),
            )
            if scores:
                metric_id = cursor.lastrowid
                conn.execute(
                    """
                    INSERT INTO detailed_scores (metric_id, scores, n_samples)
                    VALUES (?, ?, ?);
                    """,
                    (metric_id, json.dumps(scores), len(scores)),)
            conn.commit()
        return METRIC_INSERTED

    except Exception as e:
        print("ERROR:", e)
        raise