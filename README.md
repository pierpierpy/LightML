# ⚡ LightML

**Lightweight experiment tracking for LLM evaluation.**

*Three days into your experiment sprint: models scattered across five directories, evaluation results in a notebook you can't find, and that one promising checkpoint you forgot to save. Sound familiar? LightML is a zero-config experiment tracker that turns that mess into structured, searchable, exportable knowledge -- in four lines of Python.*

```
pip install light-ml-registry
lightml init --path ./my_registry --name main
```

![Dashboard overview](assets/dashboard_overview.jpg)
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
  - [Detailed scores](#detailed-scores)
  - [Statistical testing](#statistical-testing)
  - [Bulk metric logging](#bulk-metric-logging)
  - [Model deletion](#model-deletion)
  - [Metric deduplication](#metric-deduplication)
  - [Compare models](#compare-models)
  - [Auto-import (scan)](#auto-import-scan)
- [CLI Reference](#cli-reference)
  - [diff — Compare N models side-by-side](#diff--compare-n-models-side-by-side)
  - [stats — Statistical comparison](#stats--statistical-comparison)
  - [migrate — Database migration](#migrate--database-migration)
  - [version — Show version](#version--show-version)
- [Dashboard (GUI)](#dashboard-gui)
  - [Table View](#table-view)
  - [Graph View](#graph-view)
  - [Model Selection & Compare](#model-selection--compare)
  - [Excel Export](#excel-export-1)
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
| Setup | `pip install light-ml-registry` | Server + DB | Cloud signup |
| Storage | Single SQLite file | Postgres/MySQL | Cloud |
| Dependencies | 4 packages | 20+ packages | API key required |
| Dashboard | Built-in (`lightml gui`) | Separate server | Web app |
| Excel export | Built-in | No | No |
| Offline | ✅ | Partially | ❌ |

LightML is ideal when you need structured experiment tracking without the infrastructure.

---

## Installation

### From PyPI (recommended)

```bash
pip install light-ml-registry
```

### From source (development)

```bash
git clone <repo-url> && cd LightML
pip install -e ".[dev]"
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

![Quick start dashboard](assets/quick_start_gui.gif)
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

#### `register_model(model_name, path, parent_name=None, parent_id=None)`

Register a model in the current run. Idempotent — calling twice with the same name is safe.

Parent linkage can be specified by name (`parent_name`) or by database id (`parent_id`). Using `parent_id` avoids name-mismatch issues when the parent was registered with a different name convention.

```python
handle.register_model(
    model_name="llama-sft",
    path="/models/llama-3-8b-sft",
    parent_name="llama-base",  # optional: link to parent model
)

# Or link by id (useful in automation pipelines)
parent_id = handle.register_model(model_name="llama-base", path="/models/llama-base")
handle.register_model(
    model_name="llama-sft",
    path="/models/llama-sft",
    parent_id=parent_id,
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

#### `find_checkpoint(model_name, step, path_hint=None)`

Look up a checkpoint id by model name and step. When multiple checkpoints share the same step (e.g. grid search), `path_hint` disambiguates by matching against the stored path.

```python
ckpt_id = handle.find_checkpoint(
    model_name="llama-sft",
    step=5000,
    path_hint="EXP1234T5678",  # optional: disambiguate
)
```

#### `log_model_metric(model_name, family, metric_name, value, scores=None, force=False)`

Log a metric on a model. Returns a status code. Optionally attach per-sample `scores` (a list of 0/1 values) for statistical testing (see [Statistical testing](#statistical-testing)).

```python
from lightml.metrics import METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED

rc = handle.log_model_metric(
    model_name="llama-sft",
    family="mmlu_5shot",
    metric_name="mmlu_acc",
    value=0.634,
    scores=[1, 0, 1, 1, 0, ...],  # optional: per-sample binary scores
    force=False,  # True = overwrite if exists
)

if rc == METRIC_INSERTED:  print("New metric logged")
if rc == METRIC_SKIPPED:   print("Already existed, skipped")
if rc == METRIC_UPDATED:   print("Overwritten (force=True)")
```

#### `log_checkpoint_metric(checkpoint_id, family, metric_name, value, scores=None, force=False)`

Same as above, but attached to a checkpoint instead of a model.

```python
handle.log_checkpoint_metric(
    checkpoint_id=ckpt_id,
    family="hellaswag_0shot",
    metric_name="hellaswag_acc_norm",
    value=0.412,
    scores=[1, 1, 0, 1, ...],  # optional
)
```

### Detailed Scores

When you log a metric with `scores=[1, 0, 1, ...]`, LightML stores the per-sample binary vector in a dedicated `detailed_scores` table. This enables:

- **McNemar's test** — exact binomial test on discordant pairs
- **Bootstrap confidence intervals** — 95% CI on the accuracy delta
- **Contingency tables** — how many samples both models get right/wrong

Scores are stored as JSON and linked 1:1 to the metric row.

```python
# Log with detailed scores
handle.log_model_metric(
    model_name="llama-sft",
    family="hellaswag_0shot",
    metric_name="hellaswag_acc_norm",
    value=0.75,
    scores=[1, 1, 0, 1, 0, 1, 1, 1],  # 6/8 = 0.75
)

# Retrieve stored scores
scores = handle.get_detailed_scores(
    model_name="llama-sft",
    family="hellaswag_0shot",
    metric_name="hellaswag_acc_norm",
)
```

### Statistical Testing

Compare two models with rigorous statistical tests using their stored per-sample scores:

```python
result = handle.compare_stats(
    model_a="llama-base",
    model_b="llama-sft",
    family="hellaswag_0shot",
    metric_name="hellaswag_acc_norm",
)

print(result["contingency"])  # both_correct, only_a, only_b, both_wrong
print(result["mcnemar"])      # p_value, significant, winner
print(result["bootstrap"])    # delta, ci_lower, ci_upper
print(result["mean_a"], result["mean_b"])
```

The result dict contains:

| Key | Description |
|---|---|
| `contingency` | 2×2 contingency table: `both_correct`, `only_a`, `only_b`, `both_wrong`, `n_discordant` |
| `mcnemar` | McNemar's exact test: `p_value`, `significant` (p < 0.05), `winner` (`"a"` or `"b"`) |
| `bootstrap` | Bootstrap CI (10k resamples): `delta` (A−B), `ci_lower`, `ci_upper`, `confidence` |
| `mean_a` / `mean_b` | Accuracy of each model |

Also available as an interactive CLI — see [`lightml stats`](#stats--statistical-comparison).

### Bulk Metric Logging

Instead of calling `log_model_metric()` once per metric, use `log_metrics()` to log an entire evaluation result in one call:

```python
# Nested dict: {family: {metric_name: value}}
counts = handle.log_metrics("llama-sft", {
    "ENG 5-shot": {"MMLU": 56.2, "ARC": 48.7, "HellaSwag": 71.9},
    "ITA 0-shot": {"MMLU": 52.8, "HellaSwag": 62.1},
})

print(counts)  # {"inserted": 5, "updated": 0, "skipped": 0}
```

For a single family, use the flat variant:

```python
counts = handle.log_metrics_flat("llama-sft", {
    "MMLU": 56.2,
    "ARC": 48.7,
}, family="ENG 5-shot")
```

Both methods support `force=True` to overwrite existing metrics, and return a summary dict with insert/update/skip counts.

### Compare Models

Compare two models side-by-side to see per-metric deltas:

```python
from lightml.compare import compare_models

result = compare_models(
    db="./registry/main.db",
    model_a="llama-base",      # baseline
    model_b="llama-sft",       # candidate
    run_name="my-experiment",  # optional filter
    family="ENG 5-shot",       # optional filter
)

# Convenience properties
print(f"Improved: {len(result.improved)}")
print(f"Regressed: {len(result.regressed)}")
print(f"Unchanged: {len(result.unchanged)}")
print(f"Missing: {len(result.missing)}")

# Pretty terminal output (color-coded)
print(result.to_text())

# JSON-serializable dict (for APIs)
data = result.to_dict()
```

Each delta contains `family`, `metric_name`, `value_a`, `value_b`, `delta` (B−A), and `pct_change`.

### Auto-import (Scan)

Bulk-import eval results from a directory tree without writing any Python:

```python
from lightml.scan import scan_and_import

stats = scan_and_import(
    db="./registry/main.db",
    run_name="lm-eval-run",
    path="./eval_results",         # each subfolder = one model
    format="lm_eval",              # or "json"
    model_prefix="eval/",          # optional prefix
    force=False,                   # True = overwrite duplicates
)

print(f"Models: {stats.models_registered}")
print(f"Metrics: {stats.metrics_logged}")
print(f"Skipped: {stats.skipped_dirs}")
```

**Directory layout expected:**
```
eval_results/
├── model-alpha/
│   └── results_2026-01-15T10-30-00.json   # lm_eval format
├── model-beta/
│   └── results_2026-01-16T09-00-00.json
└── model-gamma/
│   └── metrics.json                        # generic JSON format
```

**Supported formats:**
| Format | File pattern | Structure |
|---|---|---|
| `lm_eval` | `results_*.json` | `{"results": {"task": {"metric": value}}}` |
| `json` | `metrics*.json` / `*.json` | `{"metric": value}` or `{"family": {"metric": value}}` |

### Model Deletion

Delete a model and all its associated data (checkpoints, metrics, detailed scores) in a single cascade operation:

```python
from lightml.models.delete import DeleteResult

result = handle.delete_model(model_name="llama-sft")

print(result.model_name)           # "llama-sft"
print(result.checkpoints_deleted)  # 5
print(result.metrics_deleted)      # 80
```

The deletion:
- Removes the model row (cascade deletes checkpoints + metrics + detailed scores via foreign keys)
- Removes the symlink from the registry `models/` directory (if present)
- Raises `ValueError` if the model doesn't exist
- Does **not** delete child models — they keep their `parent_id` reference but become orphans

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

### `scan` — Auto-import eval results

Scan a directory tree and bulk-import models + metrics:

```bash
lightml scan \
    --db ./registry/main.db \
    --run lm-eval-run \
    --path ./eval_results \
    --format lm_eval              # or "json"
    --prefix "eval/"              # optional model name prefix
    --force                       # optional: overwrite duplicates
```

Each immediate subdirectory of `--path` is treated as one model.

### `compare` — Compare two models

Print a side-by-side metric delta table:

```bash
lightml compare \
    --db ./registry/main.db \
    --model-a llama-base \
    --model-b llama-sft \
    --run my-experiment           # optional
    --family "ENG 5-shot"         # optional
```

Output:
```
  Compare: llama-base  vs  llama-sft
  Run: my-experiment
  ──────────────────────────────────────────────────────────────────────────
  Family             Metric              A          B          Δ        %
  ──────────────────────────────────────────────────────────────────────────
  ENG 5-shot         MMLU            52.10      56.20      +4.10    +7.9%
  ENG 5-shot         ARC             44.30      48.70      +4.40    +9.9%
  ENG 5-shot         HellaSwag       69.50      71.90      +2.40    +3.5%
  ──────────────────────────────────────────────────────────────────────────
  ✅ 3 improved  ❌ 0 regressed  ➖ 0 unchanged  ❓ 0 missing
```

### `diff` — Compare N models side-by-side

Print a colorized table comparing metrics across two or more models — like `git diff` but for metrics. No browser needed.

```bash
lightml diff \
    --db ./registry/main.db \
    --models llama-base llama-sft gemma-9b \
    --run my-experiment           # optional
    --family "ENG 5-shot"         # optional
    --no-color                    # optional: disable colors (for piping)
```

Output:
```
  lightml diff — 3 models  (run: my-experiment)
  ══════════════════════════════════════════════════════════════════════
  Family       Metric       llama-base     llama-sft      gemma-9b
  ──────────────────────────────────────────────────────────────────────
  ENG 5-shot   ARC              0.4430        0.4870        0.5120    ← green (best)
  ENG 5-shot   HellaSwag        0.6950        0.7190        0.7340
  ENG 5-shot   MMLU             0.5210        0.5620        0.5480
  ──────────────────────────────────────────────────────────────────────
  AVG          (3 metrics)      0.5530        0.5893        0.5980
```

- Best value per metric is highlighted in **green**, worst in **red** (when 3+ models)
- Metrics are grouped by family with blank-line separators
- An **AVG** row summarizes all metrics where every model has a value
- Missing metrics are shown as `—`

Also available as a Python API:
```python
from lightml.diff import diff_models, format_diff

data = diff_models(
    db="./registry/main.db",
    model_names=["llama-base", "llama-sft", "gemma-9b"],
    run_name="my-experiment",
    family="ENG 5-shot",
)
print(format_diff(data))
```

### `stats` — Statistical comparison

Interactively compare two models using McNemar's test and bootstrap confidence intervals. Requires detailed scores (logged with the `scores` parameter).

```bash
lightml stats --db ./registry/main.db
```

The command walks you through selecting models and metrics interactively. Or specify everything on the command line:

```bash
lightml stats \
    --db ./registry/main.db \
    --model-a llama-base \
    --model-b llama-sft \
    --family hellaswag_0shot \
    --metric hellaswag_acc_norm
```

Output:
```
  Statistical comparison: llama-base vs llama-sft
  Family: hellaswag_0shot  Metric: hellaswag_acc_norm
  ──────────────────────────────────────────────────────
  Both correct:    7234
  Only llama-base: 312
  Only llama-sft:  487
  Both wrong:      1967
  Discordant:      799
  ──────────────────────────────────────────────────────
  Mean llama-base: 0.7546
  Mean llama-sft:  0.7721
  Delta (A - B):   -0.0175
  95% CI:          [-0.0264, -0.0087]
  ──────────────────────────────────────────────────────
  McNemar p-value: 0.000012
  Result:          Significant (p < 0.05), llama-sft is better
```

### `migrate` — Database migration

Apply pending schema migrations to an older database (e.g. add the `detailed_scores` table introduced in v1.1.0):

```bash
lightml migrate --db ./registry/main.db
```

### `version` — Show version

```bash
lightml version
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
- **Family tabs** — one tab per metric family, plus "All Families" (properly scoped — same metric name across different families shows distinct values)
- **Sorting** — click any column header
- **Search** — filter models by name
- **Color coding** — best values highlighted in green, worst in red
- **Checkpoints toggle** — show/hide checkpoint rows
- **Run filter** — dropdown to isolate a specific run
- **Model selection** — checkbox column for selecting models

![Table view](assets/table_view.jpg)
<!-- GIF: switch between family tabs, sort columns, toggle checkpoints, filter by run -->

### Graph View

D3.js force-directed graph showing model lineage:
- **Nodes** = models, colored by run
- **Edges** = parent → child relationships
- **Checkpoints hidden by default** — toggle "Show checkpoints" in the control bar to reveal them
- **Hover** = tooltip with green/red dots showing which benchmarks have been evaluated
- **Search** — filter nodes by name, path, or run
- **Drag & zoom** — fully interactive

![Graph view](assets/graph_view.jpg)
<!-- GIF: switch to Graph tab, hover over nodes to see tooltips with benchmark dots, drag nodes, zoom in/out -->

### Model Selection & Compare

Select models from either view and compare them side-by-side:

1. **Select**: click checkboxes in the table, or click nodes in the graph — selections sync across both views
2. **Selection bar**: appears at the top showing count and actions
3. **Filter table**: click "Filter table" to show only selected models
4. **Compare**: select exactly 2 models, click "Compare" → a modal shows per-metric deltas with color-coded improvements (green) and regressions (red)
5. **Clear**: reset selection in both views

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

![Config editing](assets/step1_config.gif)
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

![Running evaluation](assets/step2_run_eval.gif)
<!-- GIF: terminal running `python run_eval.py`, show the output with benchmark progress and "✓ logged" messages -->

### Step 3 — Explore in dashboard

```bash
lightml gui --db ./my_registry/main.db
```

### Step 4 — Export report

Click **⬇ Excel** in the dashboard header, or:

```bash
lightml export --db ./my_registry/main.db
```

---

## Database Schema

LightML uses a single SQLite file with 6 tables:

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

-- Per-sample binary scores for statistical testing (v1.1.0+)
CREATE TABLE detailed_scores (
    metric_id   INTEGER NOT NULL PRIMARY KEY,
    scores      TEXT NOT NULL,       -- JSON array of 0/1 values
    n_samples   INTEGER NOT NULL,
    FOREIGN KEY(metric_id) REFERENCES metrics(id) ON DELETE CASCADE
);

-- Optional: restrict allowed metrics
CREATE TABLE registry_schema (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    family      TEXT NOT NULL,
    metric_name TEXT NOT NULL
);
```

Databases created with v1.0.x can be upgraded with `lightml migrate --db <path>` to add the `detailed_scores` table.

---

## Project Structure

```
LightML/
├── pyproject.toml              # Package config, CLI entry point
├── README.md                   # This file
│
├── lightml/                    # Library source
│   ├── __init__.py
│   ├── handle.py               # LightMLHandle — main API (incl. bulk log_metrics)
│   ├── registry.py             # Run & model registration logic
│   ├── checkpoints.py          # Checkpoint registration + find_checkpoint
│   ├── metrics.py              # Metric logging + deduplication + detailed scores
│   ├── database.py             # SQLite schema initialization + migration
│   ├── stats.py                # Statistical testing (McNemar, Bootstrap CI)
│   ├── export.py               # Excel export engine
│   ├── compare.py              # Model comparison (Pydantic models + compare_models)
│   ├── diff.py                 # N-model side-by-side diff (terminal table)
│   ├── scan.py                 # Auto-import from eval result directories
│   ├── gui.py                  # FastAPI dashboard server + /api/compare
│   ├── cli.py                  # CLI entry point (lightml command)
│   ├── models/                 # Pydantic schemas (incl. DeleteResult)
│   ├── templates/
│   │   └── dashboard.html      # Single-file SPA dashboard
│   └── tests/
│       ├── test_bugfix.py       # Core regression tests (41 tests)
│       ├── test_compare.py      # Compare feature tests (15 tests)
│       ├── test_diff.py         # Diff feature tests (17 tests)
│       ├── test_scan.py         # Scan / auto-import tests (17 tests)
│       ├── test_bulk.py         # Bulk metric API tests (15 tests)
│       ├── test_delete.py       # Model deletion tests (6 tests)
│       └── conftest.py          # Shared fixtures
│
├── examples/
│   └── lm_eval/                # End-to-end evaluation example
│       ├── run_eval.py          # lm_eval + LightML pipeline
│       └── config.yaml          # Example configuration
│
└── docs/
    └── gifs/                   # GIF recordings for README
```
