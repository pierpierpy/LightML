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


def all_models_with_scores(db, include_hidden=False):
    where = "" if include_hidden else "WHERE mo.hidden = 0"
    with sqlite3.connect(db) as conn:
        rows = conn.execute(f"""
            SELECT DISTINCT mo.model_name
            FROM detailed_scores ds
            JOIN metrics m ON ds.metric_id = m.id
            JOIN model mo ON m.model_id = mo.id
            {where}
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


def common_metrics_with_scores(db, model_a, model_b):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT DISTINCT ma.family, ma.metric_name
            FROM detailed_scores da
            JOIN metrics ma ON da.metric_id = ma.id
            JOIN model moa ON ma.model_id = moa.id
            WHERE moa.model_name = ?
            INTERSECT
            SELECT DISTINCT mb.family, mb.metric_name
            FROM detailed_scores db2
            JOIN metrics mb ON db2.metric_id = mb.id
            JOIN model mob ON mb.model_id = mob.id
            WHERE mob.model_name = ?
            ORDER BY 1, 2
        """, (model_a, model_b)).fetchall()
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


def _has_glob(s: str) -> bool:
    return "*" in s or "?" in s


def search_entries(db: str, model: str,
                   family: str | None = None,
                   metric: str | None = None,
                   run_name: str | None = None) -> list[dict]:
    """Search models/metrics using exact match or GLOB patterns.

    Returns a list of dicts with keys: model, family, metric, value, run.
    If family/metric are None, returns matching models only.
    """
    with sqlite3.connect(db) as conn:
        if family and metric:
            # Search metrics
            mo_op = "GLOB" if _has_glob(model) else "="
            f_op = "GLOB" if _has_glob(family) else "="
            m_op = "GLOB" if _has_glob(metric) else "="

            sql = f"""SELECT mo.model_name, m.family, m.metric_name, m.value, r.run_name
                      FROM metrics m
                      JOIN model mo ON m.model_id = mo.id
                      JOIN run r ON mo.run_id = r.id
                      WHERE mo.model_name {mo_op} ?
                        AND m.family {f_op} ?
                        AND m.metric_name {m_op} ?"""
            params: list = [model, family, metric]

            if run_name:
                r_op = "GLOB" if _has_glob(run_name) else "="
                sql += f" AND r.run_name {r_op} ?"
                params.append(run_name)

            sql += " ORDER BY mo.model_name, m.family, m.metric_name"
            rows = conn.execute(sql, params).fetchall()
            return [
                {"model": r[0], "family": r[1], "metric": r[2], "value": r[3], "run": r[4]}
                for r in rows
            ]
        else:
            # Search models only
            mo_op = "GLOB" if _has_glob(model) else "="
            sql = f"SELECT DISTINCT mo.model_name FROM model mo WHERE mo.model_name {mo_op} ?"
            rows = conn.execute(sql, [model]).fetchall()
            return [{"model": r[0]} for r in rows]


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


# ─────────────────────────────────────────────
# LIST / SUMMARY
# ─────────────────────────────────────────────

def list_all_models(db, run_name=None, include_hidden=False):
    hidden_filter = "" if include_hidden else "AND mo.hidden = 0"
    run_filter = "AND r.run_name = ?" if run_name else ""
    params = []
    if run_name:
        params.append(run_name)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(f"""
            SELECT mo.model_name, mo.path, mo.notes, mo.hidden,
                   r.run_name, pm.model_name AS parent_name
            FROM model mo
            JOIN run r ON mo.run_id = r.id
            LEFT JOIN model pm ON mo.parent_id = pm.id
            WHERE 1=1 {hidden_filter} {run_filter}
            ORDER BY r.run_name, mo.model_name
        """, params).fetchall()
    return [
        {"name": r[0], "path": r[1], "notes": r[2],
         "hidden": bool(r[3]), "run": r[4], "parent": r[5]}
        for r in rows
    ]


def list_all_runs(db):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT r.run_name, r.created_at, COUNT(mo.id) AS model_count
            FROM run r
            LEFT JOIN model mo ON mo.run_id = r.id
            GROUP BY r.id
            ORDER BY r.created_at DESC
        """).fetchall()
    return [{"name": r[0], "created_at": r[1], "model_count": r[2]} for r in rows]


def list_all_families(db):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT m.family,
                   COUNT(DISTINCT m.metric_name) AS metric_count,
                   COUNT(DISTINCT m.model_id)    AS model_count
            FROM metrics m
            GROUP BY m.family
            ORDER BY m.family
        """).fetchall()
    return [{"family": r[0], "metrics": r[1], "models": r[2]} for r in rows]


def get_db_summary(db):
    with sqlite3.connect(db) as conn:
        n_runs        = conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
        n_models      = conn.execute("SELECT COUNT(*) FROM model WHERE hidden = 0").fetchone()[0]
        n_hidden      = conn.execute("SELECT COUNT(*) FROM model WHERE hidden = 1").fetchone()[0]
        n_checkpoints = conn.execute("SELECT COUNT(*) FROM checkpoint").fetchone()[0]
        n_families    = conn.execute("SELECT COUNT(DISTINCT family) FROM metrics").fetchone()[0]
        n_metrics     = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        last          = conn.execute("SELECT MAX(created_at) FROM run").fetchone()[0]
    return {
        "runs": n_runs, "models": n_models, "hidden": n_hidden,
        "checkpoints": n_checkpoints, "families": n_families,
        "metrics": n_metrics, "last_updated": last,
    }


def get_model_detail(db, model_name):
    with sqlite3.connect(db) as conn:
        row = conn.execute("""
            SELECT mo.id, mo.model_name, mo.path, mo.notes, mo.hidden,
                   r.run_name, pm.model_name AS parent_name
            FROM model mo
            JOIN run r ON mo.run_id = r.id
            LEFT JOIN model pm ON mo.parent_id = pm.id
            WHERE mo.model_name = ?
            LIMIT 1
        """, (model_name,)).fetchone()
        if row is None:
            return None
        model_id = row[0]
        metrics = conn.execute("""
            SELECT family, metric_name, value
            FROM metrics
            WHERE model_id = ?
            ORDER BY family, metric_name
        """, (model_id,)).fetchall()
        checkpoints = conn.execute("""
            SELECT step, path, created_at
            FROM checkpoint
            WHERE model_id = ?
            ORDER BY step
        """, (model_id,)).fetchall()
        children = conn.execute("""
            SELECT model_name FROM model WHERE parent_id = ?
            ORDER BY model_name
        """, (model_id,)).fetchall()
    return {
        "name": row[1], "path": row[2], "notes": row[3],
        "hidden": bool(row[4]), "run": row[5], "parent": row[6],
        "metrics": [{"family": m[0], "metric": m[1], "value": m[2]} for m in metrics],
        "checkpoints": [{"step": c[0], "path": c[1], "created_at": c[2]} for c in checkpoints],
        "children": [c[0] for c in children],
    }


def get_top_models(db, family, metric, n=10, run_name=None, include_hidden=False):
    hidden_filter = "" if include_hidden else "AND mo.hidden = 0"
    run_filter = "AND r.run_name = ?" if run_name else ""
    params = [family, metric]
    if run_name:
        params.append(run_name)
    params.append(n)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(f"""
            SELECT mo.model_name, m.value, r.run_name
            FROM metrics m
            JOIN model mo ON m.model_id = mo.id
            JOIN run r ON mo.run_id = r.id
            WHERE m.family = ?
              AND m.metric_name = ?
              {run_filter}
              {hidden_filter}
            ORDER BY m.value DESC
            LIMIT ?
        """, params).fetchall()
    return [{"rank": i + 1, "model": r[0], "value": r[1], "run": r[2]}
            for i, r in enumerate(rows)]


def list_model_names(db, include_hidden=False):
    hidden_filter = "" if include_hidden else "WHERE hidden = 0"
    with sqlite3.connect(db) as conn:
        rows = conn.execute(f"""
            SELECT DISTINCT model_name FROM model {hidden_filter}
            ORDER BY model_name
        """).fetchall()
    return [r[0] for r in rows]


def list_metrics_in_family(db, family):
    with sqlite3.connect(db) as conn:
        rows = conn.execute("""
            SELECT DISTINCT metric_name
            FROM metrics WHERE family = ?
            ORDER BY metric_name
        """, (family,)).fetchall()
    return [r[0] for r in rows]


def get_metric_value_any_run(db, model_name, family, metric_name):
    with sqlite3.connect(db) as conn:
        row = conn.execute("""
            SELECT m.value
            FROM metrics m
            JOIN model mo ON m.model_id = mo.id
            WHERE mo.model_name = ?
              AND m.family = ?
              AND m.metric_name = ?
            LIMIT 1
        """, (model_name, family, metric_name)).fetchone()
    return row[0] if row else None