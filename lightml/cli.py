import argparse
import os
import sqlite3
from pathlib import Path

from lightml.handle import LightMLHandle
from lightml.export import export_excel
from lightml.registry import initialize_registry
from lightml.models.registry import RegistryInit
from lightml.compare import compare_models
from lightml.diff import diff_models, format_diff
from lightml.scan import scan_and_import
from lightml.readers import (
    get_available_runs, get_models_with_scores, get_metrics_with_scores,
    all_models_with_scores, all_metrics_with_scores,
    common_metrics_with_scores,
    check_detailed_scores_table,
    model_exists, metric_exists, run_metric_exists,
    search_entries,
    list_all_models, list_all_runs, list_all_families,
    get_db_summary, get_model_detail, get_top_models,
    get_metric_value_any_run,
    list_model_names, list_metrics_in_family,
)
from lightml.database import (
    migrate_database, rename_model, update_model_notes, prune_database,
)


# =====================================================
# DB RESOLUTION
# =====================================================

def resolve_db(db_arg: str | None) -> str:
    """Resolve the database path from multiple sources.

    Priority:
      1. --db argument
      2. LIGHTML_DB environment variable
      3. db= line in .lightml config file in the current directory
      4. Single *.db file auto-detected in the current directory
    """
    if db_arg:
        return db_arg
    env = os.environ.get("LIGHTML_DB")
    if env:
        return env
    config = Path(".lightml")
    if config.exists():
        for line in config.read_text().strip().splitlines():
            line = line.strip()
            if line.startswith("db="):
                return line[3:].strip()
    dbs = sorted(Path(".").glob("*.db"))
    if len(dbs) == 1:
        return str(dbs[0])
    print(
        "\n  Error: no database found. Specify one via:\n"
        "    --db ./path/to/registry.db\n"
        "    LIGHTML_DB=./path/to/registry.db\n"
        "    echo 'db=./path/to/registry.db' > .lightml\n"
    )
    raise SystemExit(1)


# =====================================================
# INTERACTIVE PICKERS
# =====================================================

def pick_one(prompt, options):
    """Show a numbered list and let the user pick one item."""
    print()
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    while True:
        try:
            choice = int(input(f"\n  {prompt}: ")) - 1
            if 0 <= choice < len(options):
                return options[choice]
            print(f"  Enter a number between 1 and {len(options)}")
        except (ValueError, EOFError):
            print("  Enter a valid number")


def pick_many(prompt, options, min_count=2):
    """Show a numbered list and let the user pick multiple items (comma-separated or ranges)."""
    print()
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    while True:
        raw = input(f"\n  {prompt} (e.g. 1,3,5 or 1-3): ").strip()
        selected = set()
        for part in raw.split(','):
            part = part.strip()
            if '-' in part:
                try:
                    lo, hi = part.split('-', 1)
                    for i in range(int(lo) - 1, int(hi)):
                        if 0 <= i < len(options):
                            selected.add(i)
                except ValueError:
                    continue
            else:
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(options):
                        selected.add(idx)
                except ValueError:
                    continue
        if len(selected) >= min_count:
            return [options[i] for i in sorted(selected)]
        print(f"  Select at least {min_count} item(s)")


def _require_models(db, min_count=1):
    """Fetch model names, exit if not enough."""
    models = list_model_names(db)
    if len(models) < min_count:
        print(f"\n  Need at least {min_count} model(s), found {len(models)}.\n")
        raise SystemExit(1)
    return models


def _require_families(db):
    """Fetch family list, exit if empty."""
    families = list_all_families(db)
    if not families:
        print("\n  No metric families found.\n")
        raise SystemExit(1)
    return families


# =====================================================
# EXISTING COMMANDS
# =====================================================

def cmd_migrate(args):
    db = resolve_db(args.db)
    result = migrate_database(db)
    print(f"\n  Migration complete:")
    for table, status in result.items():
        print(f"    {table}: {status}")
    print()


def cmd_stats(args):
    db = resolve_db(args.db)

    status = check_detailed_scores_table(db)
    if status == "missing":
        print("\n  This database was created with an older version of LightML")
        print("  that does not support detailed scores.")
        print("  Please re-create the database with LightML >= 1.1.0\n")
        return
    if status == "empty":
        print("\n  No detailed scores found in the database.")
        print("  Log metrics with the 'scores' parameter to use statistical tests.\n")
        return

    if not args.model_a or not args.model_b:
        models = all_models_with_scores(db, include_hidden=getattr(args, 'include_hidden', False))
        if len(models) < 2:
            print(f"\n  Need at least 2 models with detailed scores to compare.")
            print(f"  Found: {len(models)}\n")
            return
        print(f"\n  Models with detailed scores:")
        print(f"\n  Select model A:")
        model_a = pick_one("Model A", models)
        remaining = [m for m in models if m != model_a]
        print(f"\n  Select model B:")
        model_b = pick_one("Model B", remaining)
    else:
        model_a = args.model_a
        model_b = args.model_b

    if not args.family or not args.metric:
        metrics = common_metrics_with_scores(db, model_a, model_b)
        if not metrics:
            print(f"\n  No common metrics found between {model_a} and {model_b}.\n")
            return
        labels = [f"{f} / {m}" for f, m in metrics]
        print(f"\n  Available metrics:")
        for i, lbl in enumerate(labels, 1):
            print(f"    {i}. {lbl}")
        print(f"\n  Enter number(s), comma-separated ranges (1,3-5),")
        print(f"  'all', a family name (eng/ita), or glob patterns (hella*, gsm*)")
        raw = input(f"\n  Select metric(s): ").strip()

        import re, fnmatch
        selected_indices = set()

        if raw.lower() == 'all':
            selected_indices = set(range(len(labels)))
        else:
            for part in [p.strip() for p in raw.split(',')]:
                if not part:
                    continue
                range_match = re.match(r'^(\d+)(?:-(\d+))?$', part)
                if range_match:
                    lo = int(range_match.group(1)) - 1
                    hi = int(range_match.group(2)) - 1 if range_match.group(2) else lo
                    for i in range(max(0, lo), min(hi + 1, len(labels))):
                        selected_indices.add(i)
                    continue
                fam_matches = [i for i, (f, _) in enumerate(metrics) if f.lower() == part.lower()]
                if fam_matches:
                    selected_indices.update(fam_matches)
                    continue
                pat = part if '*' in part or '?' in part else f'*{part}*'
                for i, lbl in enumerate(labels):
                    if fnmatch.fnmatch(lbl.lower(), pat.lower()):
                        selected_indices.add(i)

        if not selected_indices:
            print(f"  No metrics matched.\n")
            return

        selected_metrics = [metrics[i] for i in sorted(selected_indices)]
        print(f"\n  Selected {len(selected_metrics)} metric(s):")
        for f, m in selected_metrics:
            print(f"    - {f} / {m}")
    else:
        selected_metrics = [(args.family, args.metric)]

    handle = LightMLHandle(db=db)
    overview = []
    for family, metric in selected_metrics:
        result = handle.compare_stats(
            model_a=model_a,
            model_b=model_b,
            family=family,
            metric_name=metric,
        )

        ct = result["contingency"]
        mc = result["mcnemar"]
        bs = result["bootstrap"]

        print(f"\n  Statistical comparison: {model_a} vs {model_b}")
        print(f"  Family: {family}  Metric: {metric}")
        print(f"  ──────────────────────────────────────────────")
        print(f"  Both correct:    {ct['both_correct']}")
        print(f"  Only {model_a}: {ct['only_a']}")
        print(f"  Only {model_b}: {ct['only_b']}")
        print(f"  Both wrong:      {ct['both_wrong']}")
        print(f"  Discordant:      {ct['n_discordant']}")
        print(f"  ──────────────────────────────────────────────")
        print(f"  Mean {model_a}: {result['mean_a']:.4f}")
        print(f"  Mean {model_b}: {result['mean_b']:.4f}")
        print(f"  Delta (A - B):   {bs['delta']:+.4f}")
        print(f"  95% CI:          [{bs['ci_lower']:+.4f}, {bs['ci_upper']:+.4f}]")
        print(f"  ──────────────────────────────────────────────")
        print(f"  McNemar p-value: {mc['p_value']:.6f}")

        if mc["significant"]:
            winner_name = model_a if mc["winner"] == "a" else model_b
            print(f"  Result:          Significant (p < 0.05), {winner_name} is better")
        else:
            print(f"  Result:          Not significant")

        if mc["significant"]:
            winner_label = model_a if mc["winner"] == "a" else model_b
        else:
            winner_label = "—"
        overview.append((family, metric, bs["delta"], mc["p_value"], mc["significant"], winner_label))

    if len(overview) > 1:
        metric_col = max(len(f"{f}/{m}") for f, m, *_ in overview)
        metric_col = max(metric_col, 6)
        winner_col = max((len(w) for *_, w in overview), default=6)
        winner_col = max(winner_col, 6)

        hdr_metric = "Metric".ljust(metric_col)
        hdr_delta  = "Delta".center(9)
        hdr_pval   = "p-value".center(10)
        hdr_sig    = "Sig?"
        hdr_winner = "Winner".ljust(winner_col)

        sep = "─" * (metric_col + 9 + 10 + 6 + winner_col + 12)

        print(f"\n  ┌{sep}┐")
        print(f"  │  {hdr_metric}  {hdr_delta}  {hdr_pval}  {hdr_sig}  {hdr_winner}  │")
        print(f"  ├{sep}┤")

        for family, metric, delta, pval, sig, winner in overview:
            m_str = f"{family}/{metric}".ljust(metric_col)
            d_str = f"{delta:+.4f}".rjust(9)
            p_str = f"{pval:.4f}".rjust(10) if pval >= 0.0001 else f"{pval:.2e}".rjust(10)
            s_str = " ✓  " if sig else " ✗  "
            w_str = winner.ljust(winner_col)
            print(f"  │  {m_str}  {d_str}  {p_str}  {s_str}  {w_str}  │")

        print(f"  └{sep}┘")

        n_sig = sum(1 for *_, sig, _ in overview if sig)
        a_wins = sum(1 for *_, sig, w in overview if sig and w == model_a)
        b_wins = sum(1 for *_, sig, w in overview if sig and w == model_b)
        print(f"\n  Summary: {n_sig}/{len(overview)} significant — "
              f"{model_a} wins {a_wins}, {model_b} wins {b_wins}")
    print()


def cmd_version(args):
    from importlib.metadata import version
    v = version("light-ml-registry")
    print(rf"""
  _    _       _     _   __  __ _
 | |  (_) __ _| |__ | |_|  \/  | |
 | |  | |/ _` | '_ \| __| |\/| | |
 | |__| | (_| | | | | |_| |  | | |___
 |____|_|\__, |_| |_|\__|_|  |_|_____|
         |___/
                            v{v}
""")


def cmd_init(args):
    registry = RegistryInit(
        registry_path=args.path,
        registry_name=args.name,
        metrics_schema=[],
        overwrite=args.overwrite,
    )
    db_path = initialize_registry(registry)
    print(f"Registry created at: {db_path}")


def cmd_model_register(args):
    db = resolve_db(args.db)
    handle = LightMLHandle(db=db, run_name=args.run)
    handle.register_model(model_name=args.name, path=args.path, parent_name=args.parent)
    print("Model registered.")


def cmd_checkpoint_register(args):
    db = resolve_db(args.db)
    handle = LightMLHandle(db=db, run_name=args.run)
    handle.register_checkpoint(model_name=args.model, step=args.step, path=args.path)
    print("Checkpoint registered.")


def cmd_metric_log(args):
    from lightml.metrics import METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED
    db = resolve_db(args.db)
    handle = LightMLHandle(db=db, run_name=args.run)

    if args.checkpoint:
        result = handle.log_checkpoint_metric(
            checkpoint_id=args.checkpoint,
            family=args.family,
            metric_name=args.metric,
            value=args.value,
            force=args.force,
        )
    else:
        result = handle.log_model_metric(
            model_name=args.model,
            family=args.family,
            metric_name=args.metric,
            value=args.value,
            force=args.force,
        )

    if result == METRIC_INSERTED:
        print("Metric logged.")
    elif result == METRIC_UPDATED:
        print("Metric updated (force).")
    elif result == METRIC_SKIPPED:
        print("Metric already exists, skipped. Use --force to overwrite.")


def cmd_export(args):
    db = resolve_db(args.db)
    db_path = Path(db)

    if args.output:
        output = Path(args.output)
    else:
        output = Path("report") / f"{db_path.stem}_report.xlsx"

    export_excel(db_path, output)


def cmd_model_delete(args):
    from lightml.database import delete_model
    db = resolve_db(args.db)
    name = args.name
    if not name:
        models = _require_models(db)
        print("  Select model to delete:")
        name = pick_one("Model", models)
    result = delete_model(db=db, model_name=name)
    print(result.to_text())


def cmd_compare(args):
    db = resolve_db(args.db)
    model_a = args.model_a
    model_b = args.model_b
    if not model_a or not model_b:
        models = _require_models(db, min_count=2)
        print("  Select model A:")
        model_a = pick_one("Model A", models)
        remaining = [m for m in models if m != model_a]
        print("\n  Select model B:")
        model_b = pick_one("Model B", remaining)
    result = compare_models(
        db=db,
        model_a=model_a,
        model_b=model_b,
        run_name=args.run,
        family=args.family,
    )
    print(result.to_text())


def cmd_scan(args):
    db = resolve_db(args.db)
    stats = scan_and_import(
        db=db,
        run_name=args.run,
        path=args.path,
        format=args.format,
        model_prefix=args.prefix or "",
        force=args.force,
    )
    print(f"\n  Scan complete")
    print(f"  Models registered : {stats.models_registered}")
    print(f"  Metrics logged    : {stats.metrics_logged}")
    if stats.skipped_dirs:
        print(f"  Skipped dirs      : {len(stats.skipped_dirs)}")
    if stats.errors:
        print(f"  Errors            : {len(stats.errors)}")
        for e in stats.errors:
            print(f"    - {e}")
    print()


def cmd_diff(args):
    db = resolve_db(args.db)
    model_names = args.models
    if not model_names:
        models = _require_models(db, min_count=2)
        print("  Select models to compare (at least 2):")
        model_names = pick_many("Models", models, min_count=2)
    data = diff_models(
        db=db,
        model_names=model_names,
        run_name=args.run,
        family=args.family,
    )
    print(format_diff(data, color=not args.no_color))


def cmd_exists(args):
    db = resolve_db(args.db)
    model = args.model
    family = args.family
    metric = args.metric
    run = args.run

    if not model:
        print("Error: --model is required.")
        raise SystemExit(1)

    if (family and not metric) or (metric and not family):
        print("Error: --family and --metric must be used together.")
        raise SystemExit(1)

    has_pattern = any("*" in (s or "") or "?" in (s or "")
                      for s in (model, family, metric, run))

    if has_pattern:
        results = search_entries(db, model, family, metric, run)
        if not results:
            print("  ✗ no matches")
            raise SystemExit(1)
        if family and metric:
            for r in results:
                print(f"  ✓ {r['model']}  {r['family']}/{r['metric']} = {r['value']:.4f}  (run: {r['run']})")
        else:
            for r in results:
                print(f"  ✓ {r['model']}")
        print(f"\n  {len(results)} match(es)")
        raise SystemExit(0)

    if family and metric:
        if run:
            found = run_metric_exists(db, run, model, family, metric)
            scope = f"model='{model}', run='{run}', family='{family}', metric='{metric}'"
        else:
            found = metric_exists(db, model, family, metric)
            scope = f"model='{model}', family='{family}', metric='{metric}'"
    else:
        found = model_exists(db, model)
        scope = f"model='{model}'"

    if found:
        print(f"  ✓ exists: {scope}")
    else:
        print(f"  ✗ not found: {scope}")

    raise SystemExit(0 if found else 1)


def cmd_gui(args):
    db = resolve_db(args.db)
    from server.main import launch
    launch(db_path=db, host=args.host, port=args.port, share=args.share)


# =====================================================
# NEW COMMANDS
# =====================================================

def cmd_list(args):
    db = resolve_db(args.db)
    what = args.what

    if what == "runs":
        runs = list_all_runs(db)
        if not runs:
            print("\n  No runs found.\n")
            return
        print(f"\n  {'Run':<35}  {'Models':>6}  Created")
        print(f"  {'─'*35}  {'─'*6}  {'─'*10}")
        for r in runs:
            created = (r['created_at'] or '')[:10]
            print(f"  {r['name']:<35}  {r['model_count']:>6}  {created}")
        print(f"\n  {len(runs)} run(s)\n")

    elif what == "families":
        families = list_all_families(db)
        if not families:
            print("\n  No metric families found.\n")
            return
        print(f"\n  {'Family':<25}  {'Metrics':>7}  {'Models':>6}")
        print(f"  {'─'*25}  {'─'*7}  {'─'*6}")
        for f in families:
            print(f"  {f['family']:<25}  {f['metrics']:>7}  {f['models']:>6}")
        print(f"\n  {len(families)} famil(ies)\n")

    else:  # models
        run = getattr(args, 'run', None)
        include_hidden = getattr(args, 'include_hidden', False)
        models = list_all_models(db, run_name=run, include_hidden=include_hidden)
        if not models:
            print("\n  No models found.\n")
            return
        name_w = max(len(m['name']) for m in models)
        name_w = max(name_w, 5)
        run_w  = max(len(m['run']) for m in models)
        run_w  = max(run_w, 3)
        print(f"\n  {'Model':<{name_w}}  {'Run':<{run_w}}  {'Parent':<25}  Notes")
        print(f"  {'─'*name_w}  {'─'*run_w}  {'─'*25}  {'─'*20}")
        for m in models:
            name   = m['name'] + (' [hidden]' if m['hidden'] else '')
            parent = m['parent'] or '—'
            notes  = (m['notes'] or '')[:30]
            print(f"  {name:<{name_w}}  {m['run']:<{run_w}}  {parent:<25}  {notes}")
        print(f"\n  {len(models)} model(s)\n")


def cmd_summary(args):
    db = resolve_db(args.db)
    s        = get_db_summary(db)
    runs     = list_all_runs(db)
    families = list_all_families(db)

    db_name = Path(db).name
    print(f"\n  {db_name}")
    print(f"  {'─'*45}")
    hidden_note = f"  ({s['hidden']} hidden)" if s['hidden'] else ""
    print(f"  Runs        : {s['runs']}")
    print(f"  Models      : {s['models']}{hidden_note}")
    print(f"  Checkpoints : {s['checkpoints']}")
    print(f"  Families    : {s['families']}")
    print(f"  Metrics     : {s['metrics']}")
    if s['last_updated']:
        print(f"  Updated     : {s['last_updated'][:10]}")

    if runs:
        print(f"\n  Runs:")
        for r in runs:
            print(f"    {r['name']}  ({r['model_count']} models)")

    if families:
        print(f"\n  Families:")
        for f in families:
            print(f"    {f['family']}  ({f['metrics']} metrics · {f['models']} models)")
    print()


def cmd_info(args):
    db   = resolve_db(args.db)
    model = args.model
    if not model:
        models = _require_models(db)
        print("  Select a model:")
        model = pick_one("Model", models)
    info = get_model_detail(db, model)

    if info is None:
        print(f"\n  Model '{model}' not found.\n")
        raise SystemExit(1)

    hidden = " [hidden]" if info['hidden'] else ""
    print(f"\n  Model  : {info['name']}{hidden}")
    print(f"  Run    : {info['run']}")
    print(f"  Path   : {info['path']}")
    if info['parent']:
        print(f"  Parent : {info['parent']}")
    if info['children']:
        print(f"  Children : {', '.join(info['children'])}")
    if info['notes']:
        print(f"  Notes  : {info['notes']}")

    if info['checkpoints']:
        print(f"\n  Checkpoints ({len(info['checkpoints'])}):")
        for c in info['checkpoints']:
            print(f"    step {c['step']:>6}  {c['path']}")

    if info['metrics']:
        print(f"\n  Metrics ({len(info['metrics'])}):")
        current_family = None
        for m in info['metrics']:
            if m['family'] != current_family:
                current_family = m['family']
                print(f"    [{current_family}]")
            print(f"      {m['metric']:<35} {m['value']:.4f}")
    print()


def cmd_top(args):
    db      = resolve_db(args.db)
    family  = args.family
    metric  = args.metric
    if not family:
        families = _require_families(db)
        print("  Select a metric family:")
        family = pick_one("Family", [f['family'] for f in families])
    if not metric:
        metrics = list_metrics_in_family(db, family)
        if not metrics:
            print(f"\n  No metrics in family '{family}'.\n")
            raise SystemExit(1)
        print("  Select a metric:")
        metric = pick_one("Metric", metrics)
    n       = args.n or 10
    results = get_top_models(
        db, family, metric, n=n,
        run_name=args.run,
        include_hidden=args.include_hidden,
    )

    if not results:
        print(f"\n  No results for family='{family}' metric='{metric}'.\n")
        raise SystemExit(1)

    name_w = max(len(r['model']) for r in results)
    name_w = max(name_w, 5)
    print(f"\n  Leaderboard  {family} / {metric}\n")
    print(f"  {'#':>3}  {'Model':<{name_w}}  {'Score':>8}  Run")
    print(f"  {'─'*3}  {'─'*name_w}  {'─'*8}  {'─'*20}")
    for r in results:
        print(f"  #{r['rank']:<2}  {r['model']:<{name_w}}  {r['value']:>8.4f}  {r['run']}")
    print()


def cmd_metric_get(args):
    db     = resolve_db(args.db)
    model  = args.model
    family = args.family
    metric = args.metric
    if not model:
        models = _require_models(db)
        print("  Select a model:")
        model = pick_one("Model", models)
    if not family:
        families = _require_families(db)
        print("  Select a metric family:")
        family = pick_one("Family", [f['family'] for f in families])
    if not metric:
        metrics = list_metrics_in_family(db, family)
        if not metrics:
            print(f"\n  No metrics in family '{family}'.\n")
            raise SystemExit(1)
        print("  Select a metric:")
        metric = pick_one("Metric", metrics)
    value = get_metric_value_any_run(db, model, family, metric)

    if value is None:
        if not args.raw:
            print(f"  Not found: {model} / {family} / {metric}")
        raise SystemExit(1)

    if args.raw:
        print(value)
    else:
        print(f"\n  {model}  {family}/{metric} = {value:.4f}\n")


def cmd_notes(args):
    db = resolve_db(args.db)
    model = args.model
    if not model:
        models = _require_models(db)
        print("  Select a model:")
        model = pick_one("Model", models)

    if args.set is not None:
        try:
            update_model_notes(db, model, args.set)
            print(f"  Notes updated for '{model}'.")
        except ValueError as e:
            print(f"  Error: {e}")
            raise SystemExit(1)
    else:
        info = get_model_detail(db, model)
        if info is None:
            print(f"\n  Model '{model}' not found.\n")
            raise SystemExit(1)
        notes = info['notes'] or "(no notes)"
        print(f"\n  {info['name']}: {notes}\n")


def cmd_rename(args):
    db = resolve_db(args.db)
    old = args.old
    if not old:
        models = _require_models(db)
        print("  Select model to rename:")
        old = pick_one("Model", models)
    new = args.new
    if not new:
        new = input("\n  New name: ").strip()
        if not new:
            print("  Name cannot be empty.")
            raise SystemExit(1)
    try:
        rename_model(db, old, new)
        print(f"  Renamed '{old}' → '{new}'")
    except ValueError as e:
        print(f"  Error: {e}")
        raise SystemExit(1)


def cmd_prune(args):
    db     = resolve_db(args.db)
    result = prune_database(db, dry_run=args.dry_run)

    if not result['models'] and not result['runs']:
        print("\n  Nothing to prune.\n")
        return

    if result['models']:
        print(f"\n  Models ({len(result['models'])}):")
        for name in result['models']:
            print(f"    - {name}")

    if result['runs']:
        print(f"\n  Runs ({len(result['runs'])}):")
        for name in result['runs']:
            print(f"    - {name}")

    if args.dry_run:
        print(f"\n  Dry-run: no changes made. Remove --dry-run to apply.\n")
    else:
        print(f"\n  Pruned: {len(result['models'])} model(s), {len(result['runs'])} run(s)\n")


def cmd_watch(args):
    import time
    import signal
    import datetime

    db       = resolve_db(args.db)
    interval = args.interval

    print(f"\n  Watching  {args.path}")
    print(f"  DB   : {db}")
    print(f"  Run  : {args.run}  |  Format: {args.format}  |  Interval: {interval}s")
    print(f"  Ctrl+C to stop\n")

    def _stop(sig, frame):
        print("\n  Stopped.\n")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _stop)

    while True:
        stats = scan_and_import(
            db=db,
            run_name=args.run,
            path=args.path,
            format=args.format,
            model_prefix=args.prefix or "",
            force=args.force,
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if stats.models_registered > 0 or stats.metrics_logged > 0:
            print(f"  [{ts}] +{stats.models_registered} models, +{stats.metrics_logged} metrics")
        else:
            print(f"  [{ts}] no new data", end="\r", flush=True)
        time.sleep(interval)


def cmd_merge(args):
    db  = resolve_db(args.db)
    src = args.src

    if not Path(src).exists():
        print(f"\n  Error: source database '{src}' not found.\n")
        raise SystemExit(1)

    print(f"\n  Merging {src} → {db}\n")

    total_models  = 0
    total_metrics = 0

    with sqlite3.connect(src) as src_conn:
        runs = src_conn.execute("SELECT run_name FROM run ORDER BY id").fetchall()

        for (run_name,) in runs:
            models = src_conn.execute("""
                SELECT mo.model_name, mo.path, pm.model_name AS parent_name, mo.notes
                FROM model mo
                JOIN run r ON mo.run_id = r.id
                LEFT JOIN model pm ON mo.parent_id = pm.id
                WHERE r.run_name = ?
                ORDER BY mo.id
            """, (run_name,)).fetchall()

            handle   = LightMLHandle(db=db, run_name=run_name)
            n_models = 0
            n_metrics = 0

            for (model_name, path, parent_name, notes) in models:
                handle.register_model(model_name, path=path or "", parent_name=parent_name)
                if notes:
                    update_model_notes(db, model_name, notes)
                n_models += 1

                metrics = src_conn.execute("""
                    SELECT m.family, m.metric_name, m.value
                    FROM metrics m
                    JOIN model mo ON m.model_id = mo.id
                    JOIN run r   ON mo.run_id   = r.id
                    WHERE mo.model_name = ? AND r.run_name = ?
                """, (model_name, run_name)).fetchall()

                for (family, metric_name, value) in metrics:
                    handle.log_model_metric(
                        model_name, family, metric_name, value, force=args.force
                    )
                    n_metrics += 1

            total_models  += n_models
            total_metrics += n_metrics
            print(f"  run '{run_name}': {n_models} model(s), {n_metrics} metric(s)")

    print(f"\n  Done. {total_models} model(s), {total_metrics} metric(s) processed.\n")


# =====================================================
# CLI
# =====================================================

def main():
    parser = argparse.ArgumentParser(prog="lightml")
    subparsers = parser.add_subparsers(dest="command")

    # ── version ──
    p_version = subparsers.add_parser("version", help="Show LightML version")
    p_version.set_defaults(func=cmd_version)

    # ── init ──
    p_init = subparsers.add_parser("init", help="Create a new registry")
    p_init.add_argument("--path", required=True)
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--overwrite", action="store_true")
    p_init.set_defaults(func=cmd_init)

    # ── model-register ──
    p_model = subparsers.add_parser("model-register", help="Register a model")
    p_model.add_argument("--db", default=None)
    p_model.add_argument("--run", default=None)
    p_model.add_argument("--name", required=True)
    p_model.add_argument("--path", required=True)
    p_model.add_argument("--parent")
    p_model.set_defaults(func=cmd_model_register)

    # ── model-delete ──
    p_mdel = subparsers.add_parser("model-delete", help="Delete a model and all related data")
    p_mdel.add_argument("--db", default=None)
    p_mdel.add_argument("--name", default=None, help="Model name (interactive if omitted)")
    p_mdel.set_defaults(func=cmd_model_delete)

    # ── checkpoint-register ──
    p_ckpt = subparsers.add_parser("checkpoint-register", help="Register a checkpoint")
    p_ckpt.add_argument("--db", default=None)
    p_ckpt.add_argument("--run", default=None)
    p_ckpt.add_argument("--model", required=True)
    p_ckpt.add_argument("--step", type=int, required=True)
    p_ckpt.add_argument("--path", required=True)
    p_ckpt.set_defaults(func=cmd_checkpoint_register)

    # ── metric-log ──
    p_metric = subparsers.add_parser("metric-log", help="Log a single metric")
    p_metric.add_argument("--db", default=None)
    p_metric.add_argument("--run", default=None)
    p_metric.add_argument("--family", required=True)
    p_metric.add_argument("--metric", required=True)
    p_metric.add_argument("--value", type=float, required=True)
    p_metric.add_argument("--model")
    p_metric.add_argument("--checkpoint", type=int)
    p_metric.add_argument("--force", action="store_true")
    p_metric.set_defaults(func=cmd_metric_log)

    # ── export ──
    p_export = subparsers.add_parser("export", help="Generate Excel report")
    p_export.add_argument("--db", default=None)
    p_export.add_argument("--output")
    p_export.set_defaults(func=cmd_export)

    # ── scan ──
    p_scan = subparsers.add_parser("scan", help="Auto-import eval results from a directory")
    p_scan.add_argument("--db", default=None)
    p_scan.add_argument("--run", default=None)
    p_scan.add_argument("--path", required=True)
    p_scan.add_argument("--format", default="lm_eval", choices=["lm_eval", "json"])
    p_scan.add_argument("--prefix")
    p_scan.add_argument("--force", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    # ── diff ──
    p_diff = subparsers.add_parser("diff", help="Side-by-side metric comparison for N models")
    p_diff.add_argument("--db", default=None)
    p_diff.add_argument("--models", nargs="+", default=None,
                        help="Model names (interactive if omitted)")
    p_diff.add_argument("--run")
    p_diff.add_argument("--family")
    p_diff.add_argument("--no-color", action="store_true")
    p_diff.set_defaults(func=cmd_diff)

    # ── compare ──
    p_cmp = subparsers.add_parser("compare", help="Compare metrics between two models")
    p_cmp.add_argument("--db", default=None)
    p_cmp.add_argument("--model-a", default=None, help="Baseline model (interactive if omitted)")
    p_cmp.add_argument("--model-b", default=None, help="Candidate model (interactive if omitted)")
    p_cmp.add_argument("--run")
    p_cmp.add_argument("--family")
    p_cmp.set_defaults(func=cmd_compare)

    # ── stats ──
    p_stats = subparsers.add_parser("stats", help="Statistical test (McNemar) between two models")
    p_stats.add_argument("--db", default=None)
    p_stats.add_argument("--run")
    p_stats.add_argument("--model-a")
    p_stats.add_argument("--model-b")
    p_stats.add_argument("--family")
    p_stats.add_argument("--metric")
    p_stats.add_argument("--include-hidden", action="store_true")
    p_stats.set_defaults(func=cmd_stats)

    # ── gui ──
    p_gui = subparsers.add_parser("gui", help="Launch interactive dashboard")
    p_gui.add_argument("--db", default=None)
    p_gui.add_argument("--port", type=int, default=5050)
    p_gui.add_argument("--host", default="0.0.0.0")
    p_gui.add_argument("--share", action="store_true", help="Expose via Cloudflare Tunnel")
    p_gui.set_defaults(func=cmd_gui)

    # ── exists ──
    p_exists = subparsers.add_parser("exists", help="Check if a model or metric exists")
    p_exists.add_argument("--db", default=None)
    p_exists.add_argument("--model", required=True)
    p_exists.add_argument("--family")
    p_exists.add_argument("--metric")
    p_exists.add_argument("--run")
    p_exists.set_defaults(func=cmd_exists)

    # ── migrate ──
    p_migrate = subparsers.add_parser("migrate", help="Update database schema to latest version")
    p_migrate.add_argument("--db", default=None)
    p_migrate.set_defaults(func=cmd_migrate)

    # ──────────────────────────────────────────────
    # NEW COMMANDS
    # ──────────────────────────────────────────────

    # ── list ──
    p_list = subparsers.add_parser("list", help="List models, runs, or metric families")
    p_list.add_argument("what", nargs="?", default="models",
                        choices=["models", "runs", "families"],
                        help="What to list (default: models)")
    p_list.add_argument("--db", default=None)
    p_list.add_argument("--run", help="Filter models by run name")
    p_list.add_argument("--include-hidden", action="store_true", help="Include hidden models")
    p_list.set_defaults(func=cmd_list)

    # ── summary ──
    p_summary = subparsers.add_parser("summary", help="Quick overview of the registry")
    p_summary.add_argument("--db", default=None)
    p_summary.set_defaults(func=cmd_summary)

    # ── info ──
    p_info = subparsers.add_parser("info", help="Detailed info for a single model")
    p_info.add_argument("--db", default=None)
    p_info.add_argument("--model", default=None, help="Model name (interactive if omitted)")
    p_info.set_defaults(func=cmd_info)

    # ── top ──
    p_top = subparsers.add_parser("top", help="Leaderboard: rank models by a metric")
    p_top.add_argument("--db", default=None)
    p_top.add_argument("--family", default=None, help="Metric family (interactive if omitted)")
    p_top.add_argument("--metric", default=None, help="Metric name (interactive if omitted)")
    p_top.add_argument("--n", type=int, default=10, help="Number of results (default: 10)")
    p_top.add_argument("--run", help="Filter to a specific run")
    p_top.add_argument("--include-hidden", action="store_true")
    p_top.set_defaults(func=cmd_top)

    # ── metric-get ──
    p_mget = subparsers.add_parser("metric-get", help="Read a single metric value (scriptable)")
    p_mget.add_argument("--db", default=None)
    p_mget.add_argument("--model", default=None, help="Model (interactive if omitted)")
    p_mget.add_argument("--family", default=None, help="Family (interactive if omitted)")
    p_mget.add_argument("--metric", default=None, help="Metric (interactive if omitted)")
    p_mget.add_argument("--raw", action="store_true",
                        help="Print only the numeric value (useful in scripts)")
    p_mget.set_defaults(func=cmd_metric_get)

    # ── notes ──
    p_notes = subparsers.add_parser("notes", help="Read or write notes on a model")
    p_notes.add_argument("--db", default=None)
    p_notes.add_argument("--model", default=None, help="Model (interactive if omitted)")
    p_notes.add_argument("--set", metavar="TEXT", default=None,
                         help="Set notes text (omit to read)")
    p_notes.set_defaults(func=cmd_notes)

    # ── rename ──
    p_rename = subparsers.add_parser("rename", help="Rename a model")
    p_rename.add_argument("--db", default=None)
    p_rename.add_argument("--old", default=None, help="Current model name (interactive if omitted)")
    p_rename.add_argument("--new", default=None, help="New model name (prompted if omitted)")
    p_rename.set_defaults(func=cmd_rename)

    # ── prune ──
    p_prune = subparsers.add_parser("prune", help="Remove empty models and runs")
    p_prune.add_argument("--db", default=None)
    p_prune.add_argument("--dry-run", action="store_true",
                         help="Show what would be removed without deleting")
    p_prune.set_defaults(func=cmd_prune)

    # ── watch ──
    p_watch = subparsers.add_parser(
        "watch", help="Continuously scan a directory and auto-import results"
    )
    p_watch.add_argument("--db", default=None)
    p_watch.add_argument("--path", required=True, help="Directory to watch")
    p_watch.add_argument("--run", default=None, help="Run name")
    p_watch.add_argument("--format", default="lm_eval", choices=["lm_eval", "json"])
    p_watch.add_argument("--prefix")
    p_watch.add_argument("--force", action="store_true")
    p_watch.add_argument("--interval", type=int, default=30,
                         help="Poll interval in seconds (default: 30)")
    p_watch.set_defaults(func=cmd_watch)

    # ── merge ──
    p_merge = subparsers.add_parser("merge", help="Merge another registry into this one")
    p_merge.add_argument("--db", default=None, help="Destination registry (default: auto-detect)")
    p_merge.add_argument("--src", required=True, help="Source registry to import from")
    p_merge.add_argument("--force", action="store_true",
                         help="Overwrite existing metrics instead of skipping")
    p_merge.set_defaults(func=cmd_merge)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
