
from lightml.models.registry import RegistryInit
from lightml.database import initialize_database
import sqlite3
from pathlib import Path
import os
import json


def _is_hf_path(path: str) -> bool:
    """True if *path* looks like a HuggingFace model ID (e.g. 'vidore/colpali-v1.3')."""
    return not os.path.isabs(path) and not os.path.exists(path)


def register_model(db: str,
                   run_name: str | None = None,
                   model_name: str = "",
                   path: str = "",
                   parent_name: str | None = None,
                   parent_id: int | None = None) -> int:

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            # ------------------------
            # PATH DEDUP: se esiste già un modello con lo stesso path,
            # ritorna il suo id senza creare duplicati.
            # HF model IDs are stored as-is; local paths are normalised.
            # ------------------------
            norm_path = path if _is_hf_path(path) else os.path.abspath(os.path.expanduser(path))
            existing = conn.execute(
                "SELECT id FROM model WHERE path = ?;",
                (norm_path,),
            ).fetchone()
            if existing:
                return existing[0]

            # ------------------------
            # GET RUN ID
            # ------------------------
            if run_name is None:
                run_name = "run_0"

            run_row = conn.execute(
                "SELECT id FROM run WHERE run_name = ?;",
                (run_name,),
            ).fetchone()

            if run_row is None:
                conn.execute(
                    "INSERT OR IGNORE INTO run (run_name) VALUES (?);",
                    (run_name,),
                )
                run_row = conn.execute(
                    "SELECT id FROM run WHERE run_name = ?;",
                    (run_name,),
                ).fetchone()

            run_id = run_row[0]

            # ------------------------
            # RESOLVE PARENT
            # ------------------------
            if parent_id is not None:
                # parent_id ha priorità su parent_name
                pass
            elif parent_name:
                row = conn.execute(
                    "SELECT id FROM model WHERE model_name = ?;",
                    (parent_name,),
                ).fetchone()

                if row is None:
                    raise ValueError(
                        f"Parent model '{parent_name}' not found in run '{run_name}'"
                    )

                parent_id = row[0]

            # ------------------------
            # INSERT MODEL (idempotente)
            # ------------------------
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO model (model_name, path, parent_id, run_id)
                VALUES (?, ?, ?, ?);
                """,
                (model_name, norm_path, parent_id, run_id),
            )

            if cursor.rowcount == 0:
                # già esiste (stesso nome+run)
                row = conn.execute(
                    "SELECT id FROM model WHERE model_name=? AND run_id=?;",
                    (model_name, run_id)
                ).fetchone()
                model_id = row[0]
            else:
                model_id = cursor.lastrowid
                conn.commit()
                create_model_symlink(db, run_name, model_name, path)

            return model_id

    except Exception as e:
        print("ERROR:", e)
        raise
    
    
from pathlib import Path

def create_model_symlink(db_path: str, run_name: str, model_name: str, model_path: str):

    # Skip symlink for HuggingFace model IDs (not local paths)
    if _is_hf_path(model_path):
        return

    registry_root = Path(db_path).parent
    models_dir = registry_root / "models"
    models_dir.mkdir(exist_ok=True)

    link_name = model_name
    link_path = models_dir / link_name

    if link_path.exists():
        link_path.unlink()

    link_path.symlink_to(Path(model_path).resolve())
    
    
    
def create_run(db: str,
               run_name: str,
               description: str | None = None,
               metadata: dict | None = None) -> int:

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        conn.execute(
            """
            INSERT OR IGNORE INTO run (run_name, description, metadata)
            VALUES (?, ?, ?);
            """,
            (
                run_name,
                description,
                json.dumps(metadata) if metadata else None
            )
        )

        row = conn.execute(
            "SELECT id FROM run WHERE run_name = ?;",
            (run_name,),
        ).fetchone()

    return row[0]
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