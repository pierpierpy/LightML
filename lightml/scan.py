"""
Auto-import: scan a directory tree for eval results and bulk-ingest into the DB.

Supported formats:
    - ``lm_eval``  — reads ``results_*.json`` files produced by lm-evaluation-harness.
    - ``json``     — reads generic ``{"metric_name": value}`` flat files.

Usage (Python):
    from lightml.scan import scan_and_import
    stats = scan_and_import(db, run_name, path, format="lm_eval")

Usage (CLI):
    lightml scan --db registry.db --run my-run --path ./eval_results --format lm_eval
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────

@dataclass
class ScanStats:
    models_registered: int = 0
    metrics_logged: int = 0
    skipped_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# Format adapters
# ─────────────────────────────────────────────

def _parse_lm_eval(result_dir: Path) -> dict[str, dict[str, float]] | None:
    """Parse lm-evaluation-harness result JSONs.

    Looks for ``results_*.json`` files.  Each contains a top-level
    ``results`` dict mapping task names to metric dicts.

    Returns:
        ``{family: {metric_name: value}}`` or None if nothing found.
    """
    metrics: dict[str, dict[str, float]] = {}

    # lm_eval writes results as results_YYYY-MM-DDTHH-MM-SS.json
    result_files = sorted(result_dir.glob("results_*.json"), reverse=True)
    if not result_files:
        # Fallback: look for any JSON with a "results" key
        for jf in result_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text())
                if "results" in data:
                    result_files = [jf]
                    break
            except (json.JSONDecodeError, KeyError):
                continue

    if not result_files:
        return None

    # Use the most recent file
    latest = result_files[0]
    try:
        data = json.loads(latest.read_text())
    except json.JSONDecodeError:
        return None

    results = data.get("results", {})
    if not results:
        return None

    for task_name, task_metrics in results.items():
        if not isinstance(task_metrics, dict):
            continue

        family = task_name
        extracted: dict[str, float] = {}

        for key, val in task_metrics.items():
            # Skip non-numeric and alias keys
            if not isinstance(val, (int, float)):
                continue
            if key.startswith("alias"):
                continue
            # Clean up metric name: remove ",none" suffix common in lm_eval
            clean_key = key.split(",")[0] if "," in key else key
            extracted[clean_key] = val

        if extracted:
            metrics[family] = extracted

    return metrics or None


def _parse_json(result_dir: Path) -> dict[str, dict[str, float]] | None:
    """Parse generic flat JSON metric files.

    Expects files like ``metrics.json`` with structure:
        ``{"metric_name": value, ...}``
    or:
        ``{"family_name": {"metric_name": value, ...}, ...}``
    """
    candidates = list(result_dir.glob("metrics*.json")) + list(result_dir.glob("results*.json"))
    if not candidates:
        candidates = list(result_dir.glob("*.json"))

    for jf in candidates:
        try:
            data = json.loads(jf.read_text())
        except json.JSONDecodeError:
            continue

        if not isinstance(data, dict):
            continue

        # Detect nested vs flat
        first_val = next(iter(data.values()), None) if data else None

        if isinstance(first_val, dict):
            # Nested: {family: {metric: value}}
            metrics: dict[str, dict[str, float]] = {}
            for family, fam_metrics in data.items():
                if isinstance(fam_metrics, dict):
                    extracted = {
                        k: v for k, v in fam_metrics.items()
                        if isinstance(v, (int, float))
                    }
                    if extracted:
                        metrics[family] = extracted
            if metrics:
                return metrics
        elif isinstance(first_val, (int, float)):
            # Flat: {metric: value}, use filename stem as family
            family = jf.stem
            extracted = {
                k: v for k, v in data.items()
                if isinstance(v, (int, float))
            }
            if extracted:
                return {family: extracted}

    return None


_ADAPTERS = {
    "lm_eval": _parse_lm_eval,
    "json": _parse_json,
}


# ─────────────────────────────────────────────
# Main scan function
# ─────────────────────────────────────────────

def scan_and_import(
    db: str,
    run_name: str,
    path: str,
    *,
    format: str = "lm_eval",
    model_prefix: str = "",
    force: bool = False,
) -> ScanStats:
    """Walk *path*, discover models, and ingest metrics into the DB.

    Each immediate subdirectory of *path* is treated as one model.
    The directory name becomes the model name (optionally prefixed).

    Args:
        db: Path to the LightML database.
        run_name: Run to register models under.
        path: Root directory to scan.
        format: Parser to use (``"lm_eval"`` or ``"json"``).
        model_prefix: Optional prefix prepended to folder names.
        force: Overwrite duplicate metrics.

    Returns:
        A :class:`ScanStats` summarising what was imported.
    """
    # Lazy import to avoid circular deps
    from lightml.handle import LightMLHandle

    adapter = _ADAPTERS.get(format)
    if adapter is None:
        raise ValueError(f"Unknown format '{format}'. Available: {list(_ADAPTERS)}")

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")

    h = LightMLHandle(db=db, run_name=run_name)
    stats = ScanStats()

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue

        model_name = f"{model_prefix}{entry.name}" if model_prefix else entry.name
        parsed = adapter(entry)

        if parsed is None:
            stats.skipped_dirs.append(entry.name)
            continue

        # Register model
        try:
            h.register_model(
                model_name=model_name,
                path=str(entry),
            )
        except Exception:
            # Model might already exist — that's fine
            pass

        stats.models_registered += 1

        # Log all metrics
        try:
            counts = h.log_metrics(model_name, parsed, force=force)
            stats.metrics_logged += counts["inserted"] + counts["updated"]
        except Exception as exc:
            stats.errors.append(f"{model_name}: {exc}")

    return stats
