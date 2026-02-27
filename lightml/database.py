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