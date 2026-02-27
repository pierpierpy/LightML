
from lightml.models.registry import ModelCreate, RegistryInit
from lightml.database import initialize_database
import sqlite3
from pathlib import Path
import os

from pathlib import Path
import sqlite3
import os

def register_model(db: str,
                   model_name: str,
                   path: str,
                   parent_name: str | None = None) -> int:
    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            parent_id = None

            if parent_name:
                row = conn.execute(
                    "SELECT id FROM model WHERE model_name = ?;",
                    (parent_name,),
                ).fetchone()

                parent_id = row[0] if row else -1  # invalid FK triggers DB error

            conn.execute(
                """
                INSERT INTO model (model_name, path, parent_id)
                VALUES (?, ?, ?);
                """,
                (model_name, str(path), parent_id),
            )

            conn.commit()

        return 1

    except Exception as e:
        print("ERROR:", e)
        raise


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