"""
Dashboard routes — serves the interactive HTML dashboard and its API endpoints.

Moved from lightml/gui.py into the unified server package.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from lightml.export import export_excel
from lightml.compare import compare_models

router = APIRouter(tags=["dashboard"])

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "lightml" / "templates" / "dashboard.html"


def _db(request: Request) -> str:
    return request.app.state.db_path


def _query(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index():
    return _TEMPLATE.read_text(encoding="utf-8")


@router.get("/api/data")
async def get_data(request: Request):
    db = _db(request)
    db_name = Path(db).stem

    runs = _query(db, "SELECT id, run_name, description, created_at FROM run ORDER BY id")

    models = _query(db, """
        SELECT m.id, m.model_name, m.path, m.parent_id, m.run_id,
               r.run_name
        FROM model m
        JOIN run r ON m.run_id = r.id
        ORDER BY m.id
    """)

    checkpoints = _query(db, """
        SELECT c.id, c.model_id, c.step, c.path, c.created_at,
               m.model_name
        FROM checkpoint c
        JOIN model m ON c.model_id = m.id
        ORDER BY c.model_id, c.step
    """)

    metrics = _query(db, """
        SELECT me.id, me.model_id, me.checkpoint_id,
               me.family, me.metric_name, me.value
        FROM metrics me
        ORDER BY me.family, me.metric_name
    """)

    families = _query(db, """
        SELECT DISTINCT family FROM metrics ORDER BY family
    """)

    schema = _query(db, """
        SELECT family, metric_name FROM registry_schema
        ORDER BY family, metric_name
    """)

    return JSONResponse({
        "db_name": db_name,
        "runs": runs,
        "models": models,
        "checkpoints": checkpoints,
        "metrics": metrics,
        "families": [f["family"] for f in families],
        "schema": schema,
    })


@router.get("/api/table")
async def get_table(request: Request, family: str | None = None, run_id: int | None = None):
    """Return pivoted table data for a given family, optionally filtered by run."""
    db = _db(request)

    # Get distinct metric names for family
    if family:
        metric_names = [
            r["metric_name"]
            for r in _query(db, "SELECT DISTINCT metric_name FROM metrics WHERE family = ? ORDER BY metric_name", (family,))
        ]
    else:
        metric_names = [
            r["metric_name"]
            for r in _query(db, "SELECT DISTINCT metric_name FROM metrics ORDER BY metric_name")
        ]

    # Build rows: models
    if run_id:
        model_rows = _query(db, """
            SELECT m.id, m.model_name, m.path, m.parent_id, r.run_name
            FROM model m
            JOIN run r ON m.run_id = r.id
            WHERE m.run_id = ?
            ORDER BY m.id
        """, (run_id,))
    else:
        model_rows = _query(db, """
            SELECT m.id, m.model_name, m.path, m.parent_id, r.run_name
            FROM model m
            JOIN run r ON m.run_id = r.id
            ORDER BY m.id
        """)

    # Build rows: checkpoints
    ckpt_rows = _query(db, """
        SELECT c.id, c.model_id, c.step, m.model_name
        FROM checkpoint c
        JOIN model m ON c.model_id = m.id
        ORDER BY c.model_id, c.step
    """)

    # Build metric lookup
    if family:
        raw_metrics = _query(db, "SELECT model_id, checkpoint_id, family, metric_name, value FROM metrics WHERE family = ?", (family,))
    else:
        raw_metrics = _query(db, "SELECT model_id, checkpoint_id, family, metric_name, value FROM metrics")

    model_metrics: dict[int, dict[str, float]] = {}
    ckpt_metrics: dict[int, dict[str, float]] = {}
    for m in raw_metrics:
        key = m["metric_name"] if family else f"{m['family']}/{m['metric_name']}"
        if m["model_id"]:
            model_metrics.setdefault(m["model_id"], {})[key] = m["value"]
        elif m["checkpoint_id"]:
            ckpt_metrics.setdefault(m["checkpoint_id"], {})[key] = m["value"]

    rows = []
    for mdl in model_rows:
        row = {
            "type": "model",
            "id": mdl["id"],
            "name": mdl["model_name"],
            "run": mdl["run_name"],
            "path": mdl["path"],
            "parent_id": mdl["parent_id"],
            "metrics": model_metrics.get(mdl["id"], {}),
        }
        rows.append(row)

    for ckpt in ckpt_rows:
        if run_id:
            parent_model = next((m for m in model_rows if m["id"] == ckpt["model_id"]), None)
            if not parent_model:
                continue
        row = {
            "type": "checkpoint",
            "id": ckpt["id"],
            "name": f"{ckpt['model_name']}  step-{ckpt['step']}",
            "model_name": ckpt["model_name"],
            "step": ckpt["step"],
            "metrics": ckpt_metrics.get(ckpt["id"], {}),
        }
        rows.append(row)

    return JSONResponse({
        "family": family,
        "metric_names": metric_names,
        "rows": rows,
    })


@router.get("/api/graph")
async def get_graph(request: Request):
    """Return nodes and links for the D3 force-directed graph."""
    db = _db(request)

    models = _query(db, """
        SELECT m.id, m.model_name, m.path, m.parent_id, m.run_id,
               r.run_name
        FROM model m
        JOIN run r ON m.run_id = r.id
        ORDER BY m.id
    """)

    checkpoints = _query(db, """
        SELECT c.id, c.model_id, c.step, c.path, m.model_name
        FROM checkpoint c
        JOIN model m ON c.model_id = m.id
        ORDER BY c.model_id, c.step
    """)

    # Build metric aggregates per model
    model_metrics = {}
    for row in _query(db, """
        SELECT model_id, family, metric_name, value
        FROM metrics WHERE model_id IS NOT NULL
    """):
        mid = row["model_id"]
        if mid not in model_metrics:
            model_metrics[mid] = {}
        model_metrics[mid][f"{row['family']}/{row['metric_name']}"] = row["value"]

    # Build metric aggregates per checkpoint
    ckpt_metrics = {}
    for row in _query(db, """
        SELECT checkpoint_id, family, metric_name, value
        FROM metrics WHERE checkpoint_id IS NOT NULL
    """):
        cid = row["checkpoint_id"]
        if cid not in ckpt_metrics:
            ckpt_metrics[cid] = {}
        ckpt_metrics[cid][f"{row['family']}/{row['metric_name']}"] = row["value"]

    # Build id→model_name lookup
    id_to_name = {m["id"]: m["model_name"] for m in models}

    nodes = []
    links = []

    for m in models:
        metrics = model_metrics.get(m["id"], {})
        vals = [v for v in metrics.values() if isinstance(v, (int, float))]
        avg_score = sum(vals) / len(vals) * 100 if vals else 0

        nodes.append({
            "id": m["model_name"],
            "type": "model",
            "path": m["path"],
            "run": m["run_name"],
            "parent": id_to_name.get(m["parent_id"]),
            "score": round(avg_score, 2),
            "metrics": metrics,
            "group": m["run_name"],
        })

        if m["parent_id"] and m["parent_id"] in id_to_name:
            links.append({
                "source": id_to_name[m["parent_id"]],
                "target": m["model_name"],
            })

    for c in checkpoints:
        ckpt_id = f"{c['model_name']}__step-{c['step']}"
        metrics = ckpt_metrics.get(c["id"], {})
        vals = [v for v in metrics.values() if isinstance(v, (int, float))]
        avg_score = sum(vals) / len(vals) * 100 if vals else 0

        nodes.append({
            "id": ckpt_id,
            "type": "checkpoint",
            "path": c["path"],
            "step": c["step"],
            "parent": c["model_name"],
            "score": round(avg_score, 2),
            "metrics": metrics,
            "group": c["model_name"],
        })

        links.append({
            "source": c["model_name"],
            "target": ckpt_id,
        })

    all_families = [f["family"] for f in _query(db, "SELECT DISTINCT family FROM metrics ORDER BY family")]

    return JSONResponse({"nodes": nodes, "links": links, "families": all_families})


@router.get("/api/export")
async def export_xlsx(request: Request):
    db = Path(_db(request))
    tmp = Path(tempfile.mkdtemp()) / f"{db.stem}_report.xlsx"
    export_excel(db, tmp)
    return FileResponse(
        path=str(tmp),
        filename=tmp.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/api/compare")
async def api_compare(
    request: Request,
    model_a: str = "",
    model_b: str = "",
    run: str | None = None,
    family: str | None = None,
):
    if not model_a or not model_b:
        return JSONResponse({"error": "model_a and model_b are required"}, status_code=400)
    try:
        result = compare_models(
            db=_db(request),
            model_a=model_a,
            model_b=model_b,
            run_name=run,
            family=family,
        )
        return JSONResponse(result.to_dict())
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
