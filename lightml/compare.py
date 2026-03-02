"""
Core model comparison logic.

Used by:
    - CLI   (``lightml compare``)
    - GUI   (``/api/compare``)
    - Python API  (``from lightml.compare import compare_models``)
"""

from __future__ import annotations

import sqlite3

from lightml.models.compare import MetricDelta, CompareResult  # noqa: F401


# ─────────────────────────────────────────────
# Core compare function
# ─────────────────────────────────────────────

def compare_models(
    db: str,
    model_a: str,
    model_b: str,
    run_name: str | None = None,
    family: str | None = None,
) -> CompareResult:
    """Compare metrics between two models.

    Args:
        db: Path to the SQLite database.
        model_a: Name of the first model (baseline).
        model_b: Name of the second model (candidate).
        run_name: Optional run filter. If ``None``, matches across all runs.
        family: Optional family filter. If ``None``, compares all families.

    Returns:
        A :class:`CompareResult` with per-metric deltas.

    Raises:
        ValueError: If either model is not found.
    """
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        # ── resolve model IDs ────────────────
        def _resolve(name: str) -> int:
            if run_name:
                row = conn.execute(
                    """SELECT m.id FROM model m JOIN run r ON m.run_id = r.id
                       WHERE m.model_name = ? AND r.run_name = ?""",
                    (name, run_name),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM model WHERE model_name = ?", (name,)
                ).fetchone()
            if row is None:
                ctx = f" in run '{run_name}'" if run_name else ""
                raise ValueError(f"Model '{name}' not found{ctx}")
            return row["id"]

        id_a = _resolve(model_a)
        id_b = _resolve(model_b)

        # ── gather metrics for both ──────────
        base_sql = "SELECT family, metric_name, value FROM metrics WHERE model_id = ?"
        params_a: list = [id_a]
        params_b: list = [id_b]

        if family:
            base_sql += " AND family = ?"
            params_a.append(family)
            params_b.append(family)

        rows_a = {
            (r["family"], r["metric_name"]): r["value"]
            for r in conn.execute(base_sql, params_a).fetchall()
        }
        rows_b = {
            (r["family"], r["metric_name"]): r["value"]
            for r in conn.execute(base_sql, params_b).fetchall()
        }

        # ── build deltas ─────────────────────
        all_keys = sorted(set(rows_a.keys()) | set(rows_b.keys()))
        deltas = [
            MetricDelta(
                family=fam,
                metric_name=met,
                value_a=rows_a.get((fam, met)),
                value_b=rows_b.get((fam, met)),
            )
            for fam, met in all_keys
        ]

    return CompareResult(
        model_a=model_a,
        model_b=model_b,
        run_name=run_name,
        deltas=deltas,
    )
