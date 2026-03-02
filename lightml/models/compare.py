"""
Pydantic models for the compare feature.

Usage:
    from lightml.models.compare import MetricDelta, CompareResult
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class MetricDelta(BaseModel):
    """Single metric comparison between two models."""
    family: str
    metric_name: str
    value_a: float | None
    value_b: float | None
    delta: float | None = None        # B − A
    pct_change: float | None = None   # (B − A) / A * 100

    @model_validator(mode="after")
    def _compute_delta(self) -> "MetricDelta":
        if self.value_a is not None and self.value_b is not None:
            self.delta = round(self.value_b - self.value_a, 4)
            if self.value_a != 0:
                self.pct_change = round(self.delta / abs(self.value_a) * 100, 2)
        return self


class CompareResult(BaseModel):
    """Full comparison between two models."""
    model_a: str
    model_b: str
    run_name: str | None
    deltas: list[MetricDelta] = []

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
