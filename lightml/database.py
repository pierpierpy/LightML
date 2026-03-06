from pathlib import Path
import sqlite3


def initialize_database(registry_path: str, metrics_schema, db_name: str) -> Path:

    db_path = Path(registry_path).expanduser().resolve()
    db_path.mkdir(parents=True, exist_ok=True)
    db_file = db_path / db_name

    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # =========================
        # RUN TABLE
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS run (
            id INTEGER PRIMARY KEY,
            run_name TEXT NOT NULL UNIQUE,
            description TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # =========================
        # MODEL TABLE (scoped by run)
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS model (
            id INTEGER PRIMARY KEY,
            model_name TEXT NOT NULL,
            path TEXT NOT NULL,
            parent_id INTEGER,
            run_id INTEGER NOT NULL,
            FOREIGN KEY(parent_id)
                REFERENCES model(id)
                ON DELETE SET NULL,
            FOREIGN KEY(run_id)
                REFERENCES run(id)
                ON DELETE CASCADE,
            UNIQUE(model_name, run_id)
        );
        """)

        # =========================
        # CHECKPOINT TABLE
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            step INTEGER NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(model_id)
                REFERENCES model(id)
                ON DELETE CASCADE
        );
        """)

        # =========================
        # REGISTRY SCHEMA TABLE
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS registry_schema (
            family TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            PRIMARY KEY (family, metric_name)
        );
        """)

        # =========================
        # METRICS TABLE
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY,
            model_id INTEGER,
            checkpoint_id INTEGER,
            family TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value REAL NOT NULL,
            FOREIGN KEY(model_id)
                REFERENCES model(id)
                ON DELETE CASCADE,
            FOREIGN KEY(checkpoint_id)
                REFERENCES checkpoint(id)
                ON DELETE CASCADE,
            CHECK (
                (model_id IS NOT NULL AND checkpoint_id IS NULL)
                OR
                (model_id IS NULL AND checkpoint_id IS NOT NULL)
            )
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS detailed_scores (
            metric_id   INTEGER NOT NULL PRIMARY KEY,
            scores      TEXT NOT NULL,
            n_samples   INTEGER NOT NULL,
            FOREIGN KEY(metric_id)
                REFERENCES metrics(id)
                ON DELETE CASCADE
        );
        """)
        # =========================
        # INSERT METRIC SCHEMA
        # =========================
        for entry in metrics_schema:
            family = entry["family"]
            metrics = entry["metrics"]

            for metric_name in metrics.keys():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO registry_schema (family, metric_name)
                    VALUES (?, ?);
                    """,
                    (family, metric_name),
                )

        conn.commit()

    return db_file


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────

def delete_model(db: str, model_name: str):
    """Delete a model and all its related data (checkpoints, metrics, symlink).

    The DB schema uses ``ON DELETE CASCADE`` on foreign keys, so deleting
    the model row automatically removes associated checkpoints and their
    metrics.  Model-level metrics are also cascade-deleted.

    Args:
        db: Path to the SQLite database.
        model_name: Exact name of the model to delete.

    Returns:
        DeleteResult with counts of deleted rows.

    Raises:
        ValueError: If the model doesn't exist.
    """
    from lightml.models.delete import DeleteResult

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # ── Look up model ──
        row = conn.execute(
            "SELECT id FROM model WHERE model_name = ?;",
            (model_name,),
        ).fetchone()

        if row is None:
            raise ValueError(f"Model '{model_name}' not found in database.")

        model_id = row[0]

        # ── Count what will be deleted (before cascade) ──
        checkpoint_ids = conn.execute(
            "SELECT id FROM checkpoint WHERE model_id = ?;",
            (model_id,),
        ).fetchall()
        n_checkpoints = len(checkpoint_ids)

        # Metrics: model-level + checkpoint-level
        n_metrics_model = conn.execute(
            "SELECT COUNT(*) FROM metrics WHERE model_id = ?;",
            (model_id,),
        ).fetchone()[0]

        n_metrics_ckpt = 0
        if checkpoint_ids:
            placeholders = ",".join("?" for _ in checkpoint_ids)
            ids = [c[0] for c in checkpoint_ids]
            n_metrics_ckpt = conn.execute(
                f"SELECT COUNT(*) FROM metrics WHERE checkpoint_id IN ({placeholders});",
                ids,
            ).fetchone()[0]

        n_metrics = n_metrics_model + n_metrics_ckpt

        # ── Delete (cascade handles checkpoints + metrics) ──
        conn.execute("DELETE FROM model WHERE id = ?;", (model_id,))
        conn.commit()

        # ── Remove symlink if it exists (skip for HF-style paths with '/') ──
        if "/" not in model_name:
            registry_root = Path(db).parent
            link_path = registry_root / "models" / model_name
            if link_path.is_symlink() or link_path.exists():
                link_path.unlink(missing_ok=True)

    return DeleteResult(
        model_name=model_name,
        model_id=model_id,
        checkpoints_deleted=n_checkpoints,
        metrics_deleted=n_metrics,
    )