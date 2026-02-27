import random
import shutil
import sqlite3
from pathlib import Path

from lightml.registry import initialize_registry
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle


# -------------------------------------------------
# CLEAN
# -------------------------------------------------

REGISTRY_DIR = "miia_registry"

if Path(REGISTRY_DIR).exists():
    shutil.rmtree(REGISTRY_DIR)


# -------------------------------------------------
# METRIC SCHEMA (MULTIPLE FAMILIES)
# -------------------------------------------------

metrics_schema = [
    {
        "family": "custom",
        "metrics": {
            "GENERIC ITA": "float",
            "RAG ITA": "float",
            "RAG ENG": "float",
        },
    },
    {
        "family": "eng_5shot",
        "metrics": {
            "MMLU-5": "float",
            "ARC-5": "float",
        },
    },
    {
        "family": "instruction_following",
        "metrics": {
            "IFEval-ITA": "float",
            "IFEval-ENG": "float",
        },
    },
]


# -------------------------------------------------
# INIT REGISTRY
# -------------------------------------------------

registry = RegistryInit(
    registry_path=REGISTRY_DIR,
    registry_name="main",
    metrics_schema=metrics_schema,
    overwrite=True,
)

db_path = initialize_registry(registry)


# -------------------------------------------------
# MODELS WITH LINEAGE
# -------------------------------------------------

models = [
    {"name": "MIIA-HF"},
    {"name": "MIIA-ECCOLO2", "parent": "MIIA-HF"},
    {"name": "MIIA-GAD-V1", "parent": "MIIA-ECCOLO2"},
    {"name": "MIIA-FT-FC", "parent": "MIIA-GAD-V1"},
    {"name": "MIIA-FFT-IF-V1", "parent": "MIIA-FT-FC"},
]


# -------------------------------------------------
# REGISTER EVERYTHING
# -------------------------------------------------

for m in models:

    handle = LightMLHandle(
        db=str(db_path),
        run_name=m["name"],
    )

    # ------------------
    # REGISTER MODEL
    # ------------------

    handle.register_model(
        model_name=m["name"],
        path=f"/models/{m['name']}",
        parent_name=m.get("parent"),
    )

    # ------------------
    # SIMULATE CHECKPOINTS
    # ------------------

    checkpoint_ids = []

    for step in [1000, 2000, 3000]:

        ckpt_id = handle.register_checkpoint(
            model_name=m["name"],
            step=step,
            path=f"/checkpoints/{m['name']}_step{step}.pt",
        )

        checkpoint_ids.append(ckpt_id)

        # checkpoint metric (solo custom family)
        handle.log_checkpoint_metric(
            checkpoint_id=ckpt_id,
            family="custom",
            metric_name="GENERIC ITA",
            value=round(random.uniform(40, 80), 2),
        )

    # ------------------
    # MODEL FINAL METRICS
    # ------------------

    # custom
    handle.log_model_metric(
        model_name=m["name"],
        family="custom",
        metric_name="GENERIC ITA",
        value=round(random.uniform(50, 85), 2),
    )

    handle.log_model_metric(
        model_name=m["name"],
        family="custom",
        metric_name="RAG ITA",
        value=round(random.uniform(50, 85), 2),
    )

    # eng_5shot
    handle.log_model_metric(
        model_name=m["name"],
        family="eng_5shot",
        metric_name="MMLU-5",
        value=round(random.uniform(40, 75), 2),
    )

    # instruction_following
    handle.log_model_metric(
        model_name=m["name"],
        family="instruction_following",
        metric_name="IFEval-ITA",
        value=round(random.uniform(0, 20), 2),
    )

    print("REGISTERED:", m["name"])


# -------------------------------------------------
# VERIFY DATABASE
# -------------------------------------------------

with sqlite3.connect(db_path) as conn:

    print("\nRUNS:")
    print(conn.execute("SELECT id, run_name FROM run;").fetchall())

    print("\nMODELS:")
    print(conn.execute("""
        SELECT id, model_name, parent_id, run_id
        FROM model;
    """).fetchall())

    print("\nCHECKPOINTS:")
    print(conn.execute("""
    SELECT c.id, c.model_id, c.step, r.run_name
    FROM checkpoint c
    JOIN model m ON c.model_id = m.id
    JOIN run r ON m.run_id = r.id;
""").fetchall())
    print("\nMETRICS:")
    print(conn.execute("""
        SELECT model_id, checkpoint_id, family, metric_name, value
        FROM metrics;
    """).fetchall())