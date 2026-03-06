import sqlite3
import json


def get_detailed_scores(db, model_name, run_name, family, metric_name):
    with sqlite3.connect(db) as conn:
        row = conn.execute("""
            SELECT ds.scores, ds.n_samples
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            JOIN model mo ON m.model_id = mo.id
            JOIN run r ON mo.run_id = r.id
            WHERE mo.model_name = ?
              AND r.run_name = ?
              AND m.family = ?
              AND m.metric_name = ?
        """, (model_name, run_name, family, metric_name)).fetchone()

    if row is None:
        raise ValueError(
            f"No detailed scores found for model='{model_name}', "
            f"run='{run_name}', family='{family}', metric='{metric_name}'"
        )

    return json.loads(row[0])


def get_metric_value(db, model_name, run_name, family, metric_name):
    with sqlite3.connect(db) as conn:
        row = conn.execute("""
            SELECT m.value
            FROM metrics m
            JOIN model mo ON m.model_id = mo.id
            JOIN run r ON mo.run_id = r.id
            WHERE mo.model_name = ?
              AND r.run_name = ?
              AND m.family = ?
              AND m.metric_name = ?
        """, (model_name, run_name, family, metric_name)).fetchone()

    if row is None:
        raise ValueError(
            f"No metric found for model='{model_name}', "
            f"run='{run_name}', family='{family}', metric='{metric_name}'"
        )

    return row[0]