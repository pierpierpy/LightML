from pathlib import Path
import sqlite3



def initialize_database(registry_path: str,metrics_schema,
                        db_name: str) -> Path:

    db_path = Path(registry_path).expanduser().resolve()
    db_path.mkdir(parents=True, exist_ok=True)
    db_file = db_path / db_name

    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # Fixed model table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model (
                id INTEGER PRIMARY KEY,
                model_name TEXT UNIQUE NOT NULL,
                path TEXT NOT NULL
            );
        """)
        conn.execute("""
    CREATE TABLE IF NOT EXISTS registry_schema (
        family TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        PRIMARY KEY (family, metric_name)
    );
""")
        conn.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY,
        model_id INTEGER NOT NULL,
        family TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value REAL,
        FOREIGN KEY(model_id)
            REFERENCES model(id)
            ON DELETE CASCADE,
        FOREIGN KEY(family, metric_name)
            REFERENCES registry_schema(family, metric_name)
            ON DELETE CASCADE
    );
""")
        for entry in metrics_schema:
            family = entry["family"]
            metrics = entry["metrics"]

            for metric_name in metrics.keys():
                conn.execute(
                    """
                    INSERT INTO registry_schema (family, metric_name)
                    VALUES (?, ?);
                    """,
                    (family, metric_name),
                )

        conn.commit()

    return db_file