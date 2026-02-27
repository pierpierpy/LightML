import os
import random
import sqlite3
from pathlib import Path

from lightml.registry import initialize_registry
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle


# ----------------------
# CLEAN PREVIOUS RUN
# ----------------------

if Path("my_registry").exists():
    import shutil
    shutil.rmtree("my_registry")


# ----------------------
# INITIALIZE REGISTRY
# ----------------------

registry = RegistryInit(
    registry_path="my_registry",
    registry_name="main",   # NO .db
    metrics_schema=[
        {
            "family": "benchmarks_ita",
            "metrics": {"Hella": "float", "MMLU": "float"},
        }
    ],
    overwrite=True,
)

db_path = initialize_registry(registry)

print("DB CREATED AT:", db_path)
print("EXISTS?", os.path.exists(db_path))


# ----------------------
# HANDLE
# ----------------------

handle = LightMLHandle(str(db_path))


# ----------------------
# REGISTER MODEL
# ----------------------

handle.register_model(
    model_name="demo_model",
    path="models/demo_model",
)


# ----------------------
# SIMULATE TRAINING
# ----------------------

best_acc = 0.0
best_ckpt_id = None

for step in [1000, 2000, 3000, 4000, 5000]:

    ckpt_id = handle.register_checkpoint(
        model_name="demo_model",
        step=step,
        path=f"checkpoints/ckpt_{step}.pt",
    )

    acc = round(random.uniform(0.7, 0.95), 4)

    handle.log_checkpoint_metric(
        checkpoint_id=ckpt_id,
        family="benchmarks_ita",
        metric_name="Hella",
        value=acc,
    )

    print("STEP", step, "ACC", acc)

    if acc > best_acc:
        best_acc = acc
        best_ckpt_id = ckpt_id


# ----------------------
# PROMOTE BEST
# ----------------------

handle.register_model(
    model_name="demo_model_best",
    path="checkpoints/best.pt",
    parent_name="demo_model",
)

handle.log_model_metric(
    model_name="demo_model_best",
    family="benchmarks_ita",
    metric_name="Hella",
    value=best_acc,
)


# ----------------------
# VERIFY DB
# ----------------------

with sqlite3.connect(db_path) as conn:
    print("\nMODELS:")
    print(conn.execute("SELECT * FROM model;").fetchall())

    print("\nCHECKPOINTS:")
    print(conn.execute("SELECT * FROM checkpoint;").fetchall())

    print("\nMETRICS:")
    print(conn.execute("SELECT * FROM metrics;").fetchall())