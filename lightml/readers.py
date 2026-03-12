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


def get_detailed_scores_any_run(db, model_name, family, metric_name):
    with sqlite3.connect(db) as conn:
        row = conn.execute("""
            SELECT ds.scores, ds.n_samples
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            JOIN model mo ON m.model_id = mo.id
            WHERE mo.model_name = ?
              AND m.family = ?
              AND m.metric_name = ?
        """, (model_name, family, metric_name)).fetchone()

    if row is None:
        raise ValueError(
            f"No detailed scores found for model='{model_name}', "
            f"family='{family}', metric='{metric_name}'"
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


def get_available_runs(db):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT run_name FROM run ORDER BY run_name").fetchall()
    return [r[0] for r in rows]


def get_models_with_scores(db, run_name):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT DISTINCT mo.model_name
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            JOIN model mo ON m.model_id = mo.id
            JOIN run r ON mo.run_id = r.id
            WHERE r.run_name = ?
            ORDER BY mo.model_name
        """, (run_name,)).fetchall()
    return [r[0] for r in rows]


def all_models_with_scores(db):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT DISTINCT mo.model_name
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            JOIN model mo ON m.model_id = mo.id
            ORDER BY mo.model_name
        """).fetchall()
    return [r[0] for r in rows]


def get_metrics_with_scores(db, run_name):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT DISTINCT m.family, m.metric_name
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            JOIN model mo ON m.model_id = mo.id
            JOIN run r ON mo.run_id = r.id
            WHERE r.run_name = ?
            ORDER BY m.family, m.metric_name
        """, (run_name,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def all_metrics_with_scores(db):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT DISTINCT m.family, m.metric_name
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            ORDER BY m.family, m.metric_name
        """).fetchall()
    return [(r[0], r[1]) for r in rows]



def model_exists(db: str, model_name: str) -> bool:
    """Check whether a model is registered (any run)."""
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT 1 FROM model WHERE model_name = ? LIMIT 1",
            (model_name,),
        ).fetchone()
    return row is not None


def metric_exists(db: str, model_name: str, family: str, metric_name: str) -> bool:
    """Check whether a specific metric exists for a model (any run)."""
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """SELECT 1 FROM metrics m
               JOIN model mo ON m.model_id = mo.id
               WHERE mo.model_name = ?
                 AND m.family = ?
                 AND m.metric_name = ?
               LIMIT 1""",
            (model_name, family, metric_name),
        ).fetchone()
    return row is not None


def run_metric_exists(db: str, run_name: str, model_name: str,
                      family: str, metric_name: str) -> bool:
    """Check whether a specific metric exists for a model in a specific run."""
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """SELECT 1 FROM metrics m
               JOIN model mo ON m.model_id = mo.id
               JOIN run r ON mo.run_id = r.id
               WHERE r.run_name = ?
                 AND mo.model_name = ?
                 AND m.family = ?
                 AND m.metric_name = ?
               LIMIT 1""",
            (run_name, model_name, family, metric_name),
        ).fetchone()
    return row is not None


def check_detailed_scores_table(db):
    """Returns 'missing', 'empty', or 'ok'."""
    with sqlite3.connect(db) as conn:
        table_exists = conn.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='detailed_scores'
        """).fetchone()[0]

        if not table_exists:
            return "missing"

        count = conn.execute("SELECT COUNT(*) FROM detailed_scores").fetchone()[0]
        if count == 0:
            return "empty"

        return "ok"