
from lightml.models.registry import ModelCreate, RegistryInit
from lightml.database import initialize_database
import sqlite3
from pathlib import Path
import os

from pathlib import Path
import sqlite3
import os

def register_model(model: ModelCreate) -> int:
    try:
        db_path = Path(model.db).resolve()

        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            # insert model
            cursor = conn.execute(
                "INSERT INTO model (model_name, path) VALUES (?, ?)",
                (model.model_name, str(model.path)),
            )
            model_id = cursor.lastrowid

            # find metric tables
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'metrics_%';"
            ).fetchall()

            # create empty metric row for each family
            for (table_name,) in tables:
                conn.execute(
                    f"INSERT INTO {table_name} (model_id) VALUES (?);",
                    (model_id,),
                )

            conn.commit()

        return 1
    except Exception:
        return 0
    

def initialize_registry(registry: RegistryInit) -> Path:
    db_name = f"{registry.registry_name}.db"

    db_path = Path(registry.registry_path).expanduser().resolve()
    db_file = db_path / db_name

    if registry.overwrite and db_file.exists():
        db_file.unlink()

    return initialize_database(
        registry.registry_path,
        registry.metrics_schema,
        db_name,
    )