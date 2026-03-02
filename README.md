# ⚡ LightML

**Lightweight experiment tracking for LLM evaluation.**

LightML is a zero-config, SQLite-backed registry for tracking models, checkpoints, and metrics across evaluation runs. No servers to deploy, no MLflow overhead — just a single `.db` file that becomes your source of truth.

```
pip install -e .
lightml init --path ./my_registry --name main
```

![Dashboard overview](docs/gifs/dashboard_overview.gif)
<!-- GIF: open the dashboard, show the table view with models + metrics, click a few column headers to sort -->

---

## Table of Contents

- [Why LightML](#why-lightml)
- [Installation](#installation)
- [Quick Start (5 minutes)](#quick-start-5-minutes)
  - [1. Create a registry](#1-create-a-registry)
  - [2. Register a model and log metrics](#2-register-a-model-and-log-metrics)
  - [3. View results](#3-view-results)
  - [4. Export to Excel](#4-export-to-excel)
- [Core Concepts](#core-concepts)
- [Python API Reference](#python-api-reference)
  - [LightMLHandle](#lightmlhandle)
  - [Metric deduplication](#metric-deduplication)
- [CLI Reference](#cli-reference)
- [Dashboard (GUI)](#dashboard-gui)
- [Excel Export](#excel-export)
- [Walkthrough: lm_eval pipeline](#walkthrough-lm_eval-pipeline)
  - [Step 1 — Configure](#step-1--configure)
  - [Step 2 — Run evaluation](#step-2--run-evaluation)
  - [Step 3 — Explore in dashboard](#step-3--explore-in-dashboard)
  - [Step 4 — Export report](#step-4--export-report)
- [Database Schema](#database-schema)
- [Project Structure](#project-structure)

---

## Why LightML

| Feature | LightML | MLflow | W&B |
|---|---|---|---|
| Setup | `pip install -e .` | Server + DB | Cloud signup |
| Storage | Single SQLite file | Postgres/MySQL | Cloud |
| Dependencies | 4 packages | 20+ packages | API key required |
| Dashboard | Built-in (`lightml gui`) | Separate server | Web app |
| Excel export | Built-in | No | No |
| Offline | ✅ | Partially | ❌ |

LightML is ideal when you need structured experiment tracking without the infrastructure.

---

## Installation

```bash
git clone <repo-url> && cd LightML
pip install -e .
```

Dependencies (auto-installed):
- `pydantic` — schema validation
- `fastapi` + `uvicorn` — dashboard server
- `openpyxl` — Excel export

For the lm_eval example you also need:
```bash
pip install lm-eval pyyaml
```

---

## Quick Start (5 minutes)

### 1. Create a registry

```bash
lightml init --path ./my_registry --name main
```

This creates `./my_registry/main.db` with all required tables.

### 2. Register a model and log metrics

```python
from lightml.handle import LightMLHandle

# Connect to registry and create an experiment run
handle = LightMLHandle(db="./my_registry/main.db", run_name="gpt2-eval")

# Register the model
handle.register_model(
    model_name="gpt2-eval",
    path="openai-community/gpt2",
)

# Log metrics — family groups related metrics together
handle.log_model_metric(
    model_name="gpt2-eval",
    family="hellaswag_0shot",
    metric_name="hellaswag_acc",
    value=0.289,
)

handle.log_model_metric(
    model_name="gpt2-eval",
    family="hellaswag_0shot",
    metric_name="hellaswag_acc_norm",
    value=0.312,
)
```

### 3. View results

```bash
lightml gui --db ./my_registry/main.db --port 5050
```

Open `http://localhost:5050` in your browser.

![Quick start dashboard](docs/gifs/quick_start_gui.gif)
<!-- GIF: run `lightml gui`, browser opens, show the table with gpt2-eval metrics -->

### 4. Export to Excel

```bash
lightml export --db ./my_registry/main.db --output report.xlsx
```

Generates one sheet per metric family with automatic color-scale formatting.

---

## Core Concepts

LightML organizes data around four entities:

```
Run (experiment)
 └── Model
      ├── Metrics (family / metric_name / value)
      └── Checkpoint (step N)
           └── Metrics
```

### Run
An experiment context. Every model belongs to a run. Runs are created automatically when you instantiate `LightMLHandle`.

### Model
A trained model registered under a run. Supports **parent-child lineage** to track fine-tuning chains (e.g., `base → SFT → DPO`).

### Checkpoint
An intermediate training snapshot linked to a model. Identified by step number.

### Metrics
Numeric values attached to either a model or a checkpoint. Organized by **family** (a logical group like `"hellaswag_0shot"`) and **metric_name** (like `"hellaswag_acc"`).

---

## Python API Reference

### LightMLHandle

The main entry point. All operations go through this handle.

```python
from lightml.handle import LightMLHandle

handle = LightMLHandle(db="path/to/registry.db", run_name="my-experiment")
```

#### `register_model(model_name, path, parent_name=None)`

Register a model in the current run. Idempotent — calling twice with the same name is safe.

```python
handle.register_model(
    model_name="llama-sft",
    path="/models/llama-3-8b-sft",
    parent_name="llama-base",  # optional: link to parent model
)
```

#### `register_checkpoint(model_name, step, path)`

Register a training checkpoint.

```python
ckpt_id = handle.register_checkpoint(
    model_name="llama-sft",
    step=5000,
    path="/checkpoints/llama-sft/step-5000",
)
```

#### `log_model_metric(model_name, family, metric_name, value, force=False)`

Log a metric on a model. Returns a status code.

```python
from lightml.metrics import METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED

rc = handle.log_model_metric(
    model_name="llama-sft",
    family="mmlu_5shot",
    metric_name="mmlu_acc",
    value=0.634,
    force=False,  # True = overwrite if exists
)

if rc == METRIC_INSERTED:  print("New metric logged")
if rc == METRIC_SKIPPED:   print("Already existed, skipped")
if rc == METRIC_UPDATED:   print("Overwritten (force=True)")
```

#### `log_checkpoint_metric(checkpoint_id, family, metric_name, value, force=False)`

Same as above, but attached to a checkpoint instead of a model.

```python
handle.log_checkpoint_metric(
    checkpoint_id=ckpt_id,
    family="hellaswag_0shot",
    metric_name="hellaswag_acc_norm",
    value=0.412,
)
```

### Metric Deduplication

LightML prevents accidental duplicate metrics:

| Scenario | `force=False` (default) | `force=True` |
|---|---|---|
| Metric does not exist | INSERT → `METRIC_INSERTED` | INSERT → `METRIC_INSERTED` |
| Metric already exists | SKIP → `METRIC_SKIPPED` | UPDATE → `METRIC_UPDATED` |

This means you can safely re-run evaluation scripts without polluting your database.

---

## CLI Reference

```
lightml <command> [options]
```

### `init` — Create a new registry

```bash
lightml init --path ./registry --name main [--overwrite]
```

### `model-register` — Register a model

```bash
lightml model-register \
    --db ./registry/main.db \
    --run my-experiment \
    --name llama-sft \
    --path /models/llama-sft \
    --parent llama-base          # optional
```

### `checkpoint-register` — Register a checkpoint

```bash
lightml checkpoint-register \
    --db ./registry/main.db \
    --run my-experiment \
    --model llama-sft \
    --step 5000 \
    --path /checkpoints/step-5000
```

### `metric-log` — Log a single metric

```bash
lightml metric-log \
    --db ./registry/main.db \
    --run my-experiment \
    --model llama-sft \
    --family mmlu_5shot \
    --metric mmlu_acc \
    --value 0.634 \
    --force                      # optional: overwrite
```

### `export` — Export Excel report

```bash
lightml export --db ./registry/main.db [--output report.xlsx]
```

### `gui` — Launch dashboard

```bash
lightml gui --db ./registry/main.db [--port 5050] [--host 0.0.0.0]
```

---

## Dashboard (GUI)

LightML ships with an interactive web dashboard — no external tools needed.

```bash
lightml gui --db ./registry/main.db
```

### Table View

Pivoted metrics table with:
- **Family tabs** — one tab per metric family, plus "All Families"
- **Sorting** — click any column header
- **Search** — filter models by name
- **Color coding** — best values highlighted in green, worst in red
- **Checkpoints toggle** — show/hide checkpoint rows
- **Run filter** — dropdown to isolate a specific run

![Table view](docs/gifs/table_view.gif)
<!-- GIF: switch between family tabs, sort columns, toggle checkpoints, filter by run -->

### Graph View

D3.js force-directed graph showing model lineage:
- **Nodes** = models (blue badges) and checkpoints (yellow badges)
- **Edges** = parent-child relationships
- **Node size** = proportional to average metric score
- **Color** = grouped by run
- **Hover** = tooltip with green/red dots showing which benchmarks have been evaluated
- **Drag & zoom** — fully interactive

![Graph view](docs/gifs/graph_view.gif)
<!-- GIF: switch to Graph tab, hover over nodes to see tooltips with benchmark dots, drag nodes, zoom in/out -->

### Excel Export

Click **⬇ Excel** in the header to download a formatted `.xlsx` report directly from the dashboard.

---

## Excel Export

The export engine creates professional Excel reports from the database:

- **One sheet per metric family** — keeps related metrics grouped
- **Automatic color scales** — red → yellow → green formatting on all metric columns
- **Frozen headers** — first row + model name column stay visible while scrolling
- **Models (Phase F)** and **Checkpoints (Phase S)** on the same sheet

```python
from pathlib import Path
from lightml.export import export_excel

export_excel(
    db_path=Path("./registry/main.db"),
    output_path=Path("./report.xlsx"),
)
```

Or via CLI:
```bash
lightml export --db ./registry/main.db --output report.xlsx
```

---

## Walkthrough: lm_eval Pipeline

This walkthrough shows how to use LightML with [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) to evaluate an LLM and track results. The complete example is in [`examples/lm_eval/`](examples/lm_eval/).

### Step 1 — Configure

Edit [`examples/lm_eval/config.yaml`](examples/lm_eval/config.yaml):

```yaml
# ── LightML settings ──────────────────────────────
db:        ./my_registry/main.db
run_name:  llama-3-eval

# ── Model to evaluate ────────────────────────────
model_path: meta-llama/Llama-3-8B

# ── Evaluation matrix ────────────────────────────
lang:       [eng]
benchmarks: [hellaswag, mmlu]
shots:      [0, 5]
num_gpus:   1
```

Every field is explained inline. The key LightML fields are `db` (path to registry) and `run_name` (experiment name).

![Config editing](docs/gifs/step1_config.gif)
<!-- GIF: open config.yaml, edit db path and model_path, save -->

### Step 2 — Run evaluation

```bash
cd examples/lm_eval
python run_eval.py
```

The script does three things:
1. **Connects to LightML** and registers the model (2 lines of setup)
2. **Runs lm_eval** for each (benchmark × language × shots) combination
3. **Logs every metric** to the registry with `handle.log_model_metric()`

Here's the core LightML integration — it's just 4 API calls:

```python
from lightml.handle import LightMLHandle

# Setup — 2 lines
handle = LightMLHandle(db=cfg["db"], run_name=cfg["run_name"])
handle.register_model(model_name=cfg["run_name"], path=cfg["model_path"])

# After each benchmark completes — 1 call per metric
handle.log_model_metric(
    model_name=handle.run_name,
    family="eng_hellaswag_0shot",
    metric_name="hellaswag_acc",
    value=0.452,
)
```

![Running evaluation](docs/gifs/step2_run_eval.gif)
<!-- GIF: terminal running `python run_eval.py`, show the output with benchmark progress and "✓ logged" messages -->

### Step 3 — Explore in dashboard

```bash
lightml gui --db ./my_registry/main.db
```

![Dashboard exploration](docs/gifs/step3_dashboard.gif)
<!-- GIF: open browser, show Table view with all metrics from the run, switch to Graph view, hover a node to see benchmark dots -->

### Step 4 — Export report

Click **⬇ Excel** in the dashboard header, or:

```bash
lightml export --db ./my_registry/main.db
```

![Excel export](docs/gifs/step4_export.gif)
<!-- GIF: click Excel button in dashboard, open the downloaded .xlsx in a spreadsheet app showing color-scaled metrics -->

---

## Database Schema

LightML uses a single SQLite file with 5 tables:

```sql
-- Experiment container
CREATE TABLE run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name    TEXT UNIQUE NOT NULL,
    description TEXT,
    metadata    TEXT  -- JSON blob
);

-- Trained model, scoped to a run
CREATE TABLE model (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name  TEXT NOT NULL,
    path        TEXT,
    parent_id   INTEGER REFERENCES model(id),
    run_id      INTEGER NOT NULL REFERENCES run(id),
    UNIQUE(model_name, run_id)
);

-- Training checkpoint, linked to a model
CREATE TABLE checkpoint (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id    INTEGER NOT NULL REFERENCES model(id),
    step        INTEGER NOT NULL,
    path        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Metric value, linked to a model OR a checkpoint
CREATE TABLE metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id        INTEGER REFERENCES model(id),
    checkpoint_id   INTEGER REFERENCES checkpoint(id),
    family          TEXT NOT NULL,
    metric_name     TEXT NOT NULL,
    value           REAL NOT NULL
);

-- Optional: restrict allowed metrics
CREATE TABLE registry_schema (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    family      TEXT NOT NULL,
    metric_name TEXT NOT NULL
);
```

---

## Project Structure

```
LightML/
├── pyproject.toml              # Package config, CLI entry point
├── README.md                   # This file
│
├── lightml/                    # Library source
│   ├── __init__.py
│   ├── handle.py               # LightMLHandle — main API
│   ├── registry.py             # Run & model registration logic
│   ├── checkpoints.py          # Checkpoint registration
│   ├── metrics.py              # Metric logging + deduplication
│   ├── database.py             # SQLite schema initialization
│   ├── export.py               # Excel export engine
│   ├── gui.py                  # FastAPI dashboard server
│   ├── cli.py                  # CLI entry point (lightml command)
│   ├── models/                 # Pydantic schemas
│   ├── templates/
│   │   └── dashboard.html      # Single-file SPA dashboard
│   └── tests/
│
├── examples/
│   └── lm_eval/                # End-to-end evaluation example
│       ├── run_eval.py          # lm_eval + LightML pipeline
│       └── config.yaml          # Example configuration
│
└── docs/
    └── gifs/                   # GIF recordings for README
```

---

## GIF Recording Checklist

Record these GIFs and place them in `docs/gifs/`:

| Filename | What to record |
|---|---|
| `dashboard_overview.gif` | Open dashboard, pan around table, show it's alive |
| `quick_start_gui.gif` | After quick-start: run `lightml gui`, show table with gpt2 metrics |
| `table_view.gif` | Switch family tabs, sort columns, toggle checkpoints, filter runs |
| `graph_view.gif` | Switch to Graph, hover nodes (benchmark dots tooltip), drag, zoom |
| `step1_config.gif` | Edit config.yaml — set db path, model, benchmarks |
| `step2_run_eval.gif` | Terminal: `python run_eval.py` with benchmark output + logged messages |
| `step3_dashboard.gif` | After eval: dashboard showing all logged metrics, then graph view |
| `step4_export.gif` | Click Excel button, open the downloaded .xlsx |

