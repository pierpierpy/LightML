#!/usr/bin/env python3
"""
LightML + lm_eval — end-to-end evaluation pipeline.

Runs lm-evaluation-harness benchmarks and logs every metric straight
into a LightML registry so you can explore results with the dashboard,
export Excel reports, or compare runs programmatically.

Usage:
    python run_eval.py                 # uses config.yaml in this folder
    python run_eval.py my_config.yaml  # custom config
"""

import os
import sys
import json
import subprocess

import yaml

# ── LightML imports ─────────────────────────────────────────
from lightml.handle import LightMLHandle
from lightml.metrics import METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED

# ── Constants ───────────────────────────────────────────────
TASKS = {
    "eng": {
        "hellaswag": "hellaswag",
        "mmlu": "mmlu",
        "arc": "arc_easy,arc_challenge",
    },
    "ita": {
        "hellaswag": "itabench_hellaswag_it-it",
        "mmlu": "itabench_mmlu_multichoice_it-it",
        "arc": "itabench_arc_easy_it-it,itabench_arc_challenge_it-it",
    },
}


# ── Helpers ─────────────────────────────────────────────────

def find_latest_results(output_dir: str, model_path: str) -> dict | None:
    """Return the most-recent results_*.json written by lm_eval."""
    model_folder = model_path.replace("/", "__")
    results_dir = os.path.join(output_dir, model_folder)
    if not os.path.isdir(results_dir):
        return None
    files = sorted(
        [f for f in os.listdir(results_dir)
         if f.startswith("results_") and f.endswith(".json")],
        reverse=True,
    )
    if not files:
        return None
    with open(os.path.join(results_dir, files[0])) as fh:
        return json.load(fh)


def run_benchmark(model_path, benchmark, lang, shots, num_gpus,
                  output_dir, ita_tasks_path=None, limit=None):
    """Launch lm_eval for a single (benchmark, lang, shots) combo."""

    tasks = TASKS[lang][benchmark]
    batch = "8" if shots > 0 else "auto"

    print(f"\n{'='*60}")
    print(f"  {benchmark} | {lang} | {shots}-shot")
    print(f"{'='*60}")

    # Build command
    if num_gpus > 1:
        cmd = [
            "accelerate", "launch",
            "--num_processes", str(num_gpus), "--multi_gpu",
            "-m", "lm_eval",
        ]
    else:
        cmd = ["lm_eval"]

    cmd += [
        "--model", "hf",
        "--model_args", f"pretrained={model_path}",
        "--tasks", tasks,
        "--num_fewshot", str(shots),
        "--batch_size", batch,
        "--log_samples",
        "--output_path", output_dir,
    ]

    if num_gpus == 1:
        cmd += ["--device", "cuda:0"]
    if limit:
        cmd += ["--limit", str(limit)]
    if lang == "ita" and ita_tasks_path:
        cmd += ["--include_path", ita_tasks_path]

    # Run — stdout/stderr go to terminal for live visibility
    env = os.environ.copy()
    if num_gpus > 1:
        env["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"

    rc = subprocess.run(cmd, env=env).returncode
    if rc != 0:
        print(f"  ✗ lm_eval exited with code {rc}")
        return None

    return find_latest_results(output_dir, model_path)


def log_results(handle: LightMLHandle, results: dict,
                benchmark: str, lang: str, shots: int, force: bool):
    """
    Extract acc / acc_norm from lm_eval results and log them to LightML.

    ┌────────────────── LightML concepts used ──────────────────┐
    │  handle.log_model_metric(                                 │
    │      model_name = ...,                                    │
    │      family     = "eng_hellaswag_0shot",   ← benchmark    │
    │      metric_name= "hellaswag_acc",         ← task metric  │
    │      value      = 0.45,                                   │
    │      force      = True/False,              ← upsert flag  │
    │  )                                                        │
    └───────────────────────────────────────────────────────────┘
    """
    if not results or "results" not in results:
        return

    logged = updated = skipped = 0
    family = f"{lang}_{benchmark}_{shots}shot"

    for task_name, metrics in results["results"].items():
        if not isinstance(metrics, dict):
            continue

        for suffix in ("acc,none", "acc_norm,none"):
            if suffix not in metrics:
                continue

            short = suffix.split(",")[0]           # "acc" or "acc_norm"
            rc = handle.log_model_metric(
                model_name=handle.run_name,
                family=family,
                metric_name=f"{task_name}_{short}",
                value=metrics[suffix],
                force=force,
            )

            if   rc == METRIC_INSERTED: logged  += 1
            elif rc == METRIC_UPDATED:  updated += 1
            elif rc == METRIC_SKIPPED:  skipped += 1

    parts = []
    if logged:  parts.append(f"{logged} logged")
    if updated: parts.append(f"{updated} updated")
    if skipped: parts.append(f"{skipped} skipped")
    print(f"  ✓ {family}: {', '.join(parts) or 'no metrics'}")


# ── Main ────────────────────────────────────────────────────

def main():
    # 1. Load config
    config_path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(__file__), "config.yaml")

    if not os.path.exists(config_path):
        sys.exit(f"Config not found: {config_path}")

    cfg = yaml.safe_load(open(config_path))

    model       = cfg["model_path"]
    run_name    = cfg["run_name"]
    db          = cfg["db"]
    langs       = cfg.get("lang", ["eng"])
    benchmarks  = cfg.get("benchmarks", ["hellaswag", "mmlu", "arc"])
    shots_list  = cfg.get("shots", [0, 5])
    num_gpus    = cfg.get("num_gpus", 1)
    limit       = cfg.get("limit")
    force       = cfg.get("force", False)
    output_dir  = cfg.get("output_dir", os.path.join(os.path.dirname(__file__), "json"))
    ita_tasks   = cfg.get("ita_tasks_path")

    if isinstance(langs, str):
        langs = [langs]

    # ┌───────────────────────────────────────────────────────┐
    # │              LightML setup (2 lines)                  │
    # └───────────────────────────────────────────────────────┘
    handle = LightMLHandle(db=db, run_name=run_name)
    handle.register_model(model_name=run_name, path=model)

    print(f"\n{'#'*60}")
    print(f"#  LightML Eval Pipeline")
    print(f"#  Model:  {model}")
    print(f"#  Run:    {run_name}")
    print(f"#  DB:     {db}")
    print(f"#  Langs:  {', '.join(langs)}")
    print(f"#  Bench:  {', '.join(benchmarks)}")
    print(f"#  Shots:  {', '.join(map(str, shots_list))}")
    print(f"{'#'*60}")

    # ┌───────────────────────────────────────────────────────┐
    # │         Run benchmarks → log to LightML               │
    # └───────────────────────────────────────────────────────┘
    for lang in langs:
        for bench in benchmarks:
            for shots in shots_list:
                results = run_benchmark(
                    model, bench, lang, shots, num_gpus,
                    output_dir, ita_tasks, limit,
                )
                if results:
                    log_results(handle, results, bench, lang, shots, force)

    print(f"\n{'='*60}")
    print(f"  ✓ Done — results saved to LightML registry")
    print(f"    View: lightml gui --db {db}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
