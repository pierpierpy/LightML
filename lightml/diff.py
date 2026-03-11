"""
Side-by-side metric comparison for N models in the terminal.

Usage:
    CLI:    ``lightml diff --db registry.db --models m1 m2 m3``
    Python: ``from lightml.diff import diff_models``
"""

from __future__ import annotations

import sqlite3


# ANSI color helpers
_GREEN = "\033[32m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def diff_models(
    db: str,
    model_names: list[str],
    run_name: str | None = None,
    family: str | None = None,
) -> dict:
    """Gather metrics for N models and return structured data.

    Returns:
        {
            "models": ["m1", "m2", ...],
            "run_name": str | None,
            "rows": [
                {"family": str, "metric": str, "values": {model: float | None, ...}},
                ...
            ],
        }
    """
    if len(model_names) < 2:
        raise ValueError("Need at least 2 models to diff")

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        # Resolve model IDs
        model_ids: dict[str, int] = {}
        for name in model_names:
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
            model_ids[name] = row["id"]

        # Gather metrics per model
        metrics_by_model: dict[str, dict[tuple[str, str], float]] = {}
        for name, mid in model_ids.items():
            sql = "SELECT family, metric_name, value FROM metrics WHERE model_id = ?"
            params: list = [mid]
            if family:
                sql += " AND family = ?"
                params.append(family)
            metrics_by_model[name] = {
                (r["family"], r["metric_name"]): r["value"]
                for r in conn.execute(sql, params).fetchall()
            }

    # Collect all metric keys
    all_keys: set[tuple[str, str]] = set()
    for m in metrics_by_model.values():
        all_keys |= m.keys()

    rows = []
    for fam, met in sorted(all_keys):
        values = {name: metrics_by_model[name].get((fam, met)) for name in model_names}
        rows.append({"family": fam, "metric": met, "values": values})

    return {"models": model_names, "run_name": run_name, "rows": rows}


def format_diff(data: dict, *, color: bool = True) -> str:
    """Render diff data as a colorized terminal table."""
    models = data["models"]
    rows = data["rows"]
    run_name = data["run_name"]

    if not rows:
        return "\n  No metrics found for the given models.\n"

    # Column widths
    fam_w = max(len("Family"), max(len(r["family"]) for r in rows))
    met_w = max(len("Metric"), max(len(r["metric"]) for r in rows))
    # Model column: at least as wide as model name, or the formatted value
    val_w = max(10, max(len(m) for m in models))

    total_w = fam_w + 2 + met_w + 2 + (val_w + 2) * len(models)

    lines: list[str] = []

    # Header
    n = len(models)
    run_info = f"  (run: {run_name})" if run_name else ""
    lines.append("")
    if color:
        lines.append(f"  {_BOLD}lightml diff{_RESET} — {n} models{run_info}")
    else:
        lines.append(f"  lightml diff — {n} models{run_info}")
    lines.append(f"  {'═' * total_w}")

    # Column headers
    header = f"  {'Family':<{fam_w}}  {'Metric':<{met_w}}"
    for m in models:
        header += f"  {m:>{val_w}}"
    lines.append(header)
    lines.append(f"  {'─' * total_w}")

    # Rows
    prev_family = None
    for r in rows:
        fam_display = r["family"]
        # Group separator: blank line between families
        if prev_family is not None and fam_display != prev_family:
            lines.append("")
        prev_family = fam_display

        vals = r["values"]
        # Find best and worst among non-None values
        numeric = {m: v for m, v in vals.items() if v is not None}
        best_val = max(numeric.values()) if numeric else None
        worst_val = min(numeric.values()) if numeric else None
        # Don't highlight if all values are the same
        all_same = best_val is not None and best_val == worst_val

        line = f"  {fam_display:<{fam_w}}  {r['metric']:<{met_w}}"
        for m in models:
            v = vals[m]
            if v is None:
                cell = "—"
                formatted = f"{cell:>{val_w}}"
                if color:
                    formatted = f"{_DIM}{formatted}{_RESET}"
            else:
                cell = f"{v:.4f}"
                formatted = f"{cell:>{val_w}}"
                if color and not all_same:
                    if v == best_val:
                        formatted = f"{_GREEN}{formatted}{_RESET}"
                    elif v == worst_val and len(numeric) > 2:
                        formatted = f"{_RED}{formatted}{_RESET}"
            line += f"  {formatted}"
        lines.append(line)

    lines.append(f"  {'─' * total_w}")

    # Summary: per-model average across all metrics where all models have a value
    common_keys = [
        r for r in rows
        if all(r["values"][m] is not None for m in models)
    ]
    if common_keys:
        avgs = {}
        for m in models:
            avgs[m] = sum(r["values"][m] for r in common_keys) / len(common_keys)

        best_avg = max(avgs.values())
        worst_avg = min(avgs.values())
        avg_same = best_avg == worst_avg

        avg_line = f"  {'AVG':<{fam_w}}  {'(' + str(len(common_keys)) + ' metrics)':<{met_w}}"
        for m in models:
            cell = f"{avgs[m]:.4f}"
            formatted = f"{cell:>{val_w}}"
            if color and not avg_same:
                if avgs[m] == best_avg:
                    formatted = f"{_GREEN}{_BOLD}{formatted}{_RESET}"
                elif avgs[m] == worst_avg and len(models) > 2:
                    formatted = f"{_RED}{formatted}{_RESET}"
            avg_line += f"  {formatted}"
        lines.append(avg_line)

    lines.append("")
    return "\n".join(lines)
