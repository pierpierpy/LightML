"""
Core model comparison logic.

Used by:
    - CLI   (``lightml compare``)
    - GUI   (``/api/compare``)
    - Python API  (``from lightml.compare import compare_models``)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class MetricDelta:
    """Single metric comparison between two models."""
    family: str
    metric_name: str
    value_a: float | None
    value_b: float | None
    delta: float | None = None        # B − A
    pct_change: float | None = None   # (B − A) / A * 100

    def __post_init__(self):
        if self.value_a is not None and self.value_b is not None:
            self.delta = round(self.value_b - self.value_a, 4)
            if self.value_a != 0:
                self.pct_change = round(self.delta / abs(self.value_a) * 100, 2)


@dataclass
class CompareResult:
    """Full comparison between two models."""
    model_a: str
    model_b: str
    run_name: str | None
    deltas: list[MetricDelta] = field(default_factory=list)

    # ── convenience helpers ───────────────────

    @property
    def improved(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.delta is not None and d.delta > 0]

    @property
    def regressed(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.delta is not None and d.delta < 0]

    @property
    def unchanged(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.delta is not None and d.delta == 0]

    @property
    def missing(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.delta is None]

    def to_dict(self) -> dict:
        """Serialise for JSON responses."""
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "run": self.run_name,
            "summary": {
                "improved": len(self.improved),
                "regressed": len(self.regressed),
                "unchanged": len(self.unchanged),
                "missing": len(self.missing),
            },
            "deltas": [
                {
                    "family": d.family,
                    "metric": d.metric_name,
                    "value_a": d.value_a,
                    "value_b": d.value_b,
                    "delta": d.delta,
                    "pct_change": d.pct_change,
                }
                for d in self.deltas
            ],
        }

    def to_text(self, *, color: bool = True) -> str:
        """Pretty-print for terminal output."""
        lines: list[str] = []
        lines.append(f"\n  Compare: {self.model_a}  vs  {self.model_b}")
        if self.run_name:
            lines.append(f"  Run: {self.run_name}")
        lines.append(f"  {'─' * 70}")
        lines.append(f"  {'Family':<18} {'Metric':<14} {'A':>10} {'B':>10} {'Δ':>10} {'%':>8}")
        lines.append(f"  {'─' * 70}")

        for d in self.deltas:
            va = f"{d.value_a:.2f}" if d.value_a is not None else "—"
            vb = f"{d.value_b:.2f}" if d.value_b is not None else "—"

            if d.delta is not None:
                delta_str = f"{d.delta:+.2f}"
                pct_str = f"{d.pct_change:+.1f}%" if d.pct_change is not None else "—"

                if color:
                    if d.delta > 0:
                        delta_str = f"\033[32m{delta_str}\033[0m"
                        pct_str = f"\033[32m{pct_str}\033[0m"
                    elif d.delta < 0:
                        delta_str = f"\033[31m{delta_str}\033[0m"
                        pct_str = f"\033[31m{pct_str}\033[0m"
            else:
                delta_str = "—"
                pct_str = "—"

            lines.append(f"  {d.family:<18} {d.metric_name:<14} {va:>10} {vb:>10} {delta_str:>10} {pct_str:>8}")

        lines.append(f"  {'─' * 70}")
        s = self
        lines.append(
            f"  ✅ {len(s.improved)} improved  "
            f"❌ {len(s.regressed)} regressed  "
            f"➖ {len(s.unchanged)} unchanged  "
            f"❓ {len(s.missing)} missing"
        )
        lines.append("")
        return "\n".join(lines)


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
