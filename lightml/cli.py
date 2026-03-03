import argparse
from pathlib import Path

from lightml.handle import LightMLHandle
from lightml.export import export_excel
from lightml.registry import initialize_registry
from lightml.models.registry import RegistryInit
from lightml.compare import compare_models
from lightml.scan import scan_and_import


# =====================================================
# COMMANDS
# =====================================================

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
    handle = LightMLHandle(
        db=args.db,
        run_name=args.run
    )

    handle.register_model(
        model_name=args.name,
        path=args.path,
        parent_name=args.parent
    )

    print("Model registered.")


def cmd_checkpoint_register(args):
    handle = LightMLHandle(
        db=args.db,
        run_name=args.run
    )

    handle.register_checkpoint(
        model_name=args.model,
        step=args.step,
        path=args.path
    )

    print("Checkpoint registered.")


def cmd_metric_log(args):
    from lightml.metrics import METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED

    handle = LightMLHandle(
        db=args.db,
        run_name=args.run
    )

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
    db_path = Path(args.db)

    if args.output:
        output = Path(args.output)
    else:
        output = Path("report") / f"{db_path.stem}_report.xlsx"

    export_excel(db_path, output)


def cmd_model_delete(args):
    from lightml.database import delete_model

    result = delete_model(db=args.db, model_name=args.name)
    print(result.to_text())


def cmd_compare(args):
    result = compare_models(
        db=args.db,
        model_a=args.model_a,
        model_b=args.model_b,
        run_name=args.run,
        family=args.family,
    )
    print(result.to_text())


def cmd_scan(args):
    stats = scan_and_import(
        db=args.db,
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


def cmd_gui(args):
    from server.main import launch
    launch(db_path=args.db, host=args.host, port=args.port)


# =====================================================
# CLI
# =====================================================

def main():

    parser = argparse.ArgumentParser(prog="lightml")
    subparsers = parser.add_subparsers(dest="command")

    # INIT
    p_init = subparsers.add_parser("init")
    p_init.add_argument("--path", required=True)
    p_init.add_argument("--name", required=True)
    p_init.add_argument("--overwrite", action="store_true")
    p_init.set_defaults(func=cmd_init)

    # MODEL REGISTER
    p_model = subparsers.add_parser("model-register")
    p_model.add_argument("--db", required=True)
    p_model.add_argument("--run", required=True)
    p_model.add_argument("--name", required=True)
    p_model.add_argument("--path", required=True)
    p_model.add_argument("--parent")
    p_model.set_defaults(func=cmd_model_register)

    # MODEL DELETE
    p_mdel = subparsers.add_parser("model-delete", help="Delete a model and all related data")
    p_mdel.add_argument("--db", required=True)
    p_mdel.add_argument("--name", required=True, help="Model name to delete")
    p_mdel.set_defaults(func=cmd_model_delete)

    # CHECKPOINT REGISTER
    p_ckpt = subparsers.add_parser("checkpoint-register")
    p_ckpt.add_argument("--db", required=True)
    p_ckpt.add_argument("--run", required=True)
    p_ckpt.add_argument("--model", required=True)
    p_ckpt.add_argument("--step", type=int, required=True)
    p_ckpt.add_argument("--path", required=True)
    p_ckpt.set_defaults(func=cmd_checkpoint_register)

    # METRIC LOG
    p_metric = subparsers.add_parser("metric-log")
    p_metric.add_argument("--db", required=True)
    p_metric.add_argument("--run", required=True)
    p_metric.add_argument("--family", required=True)
    p_metric.add_argument("--metric", required=True)
    p_metric.add_argument("--value", type=float, required=True)
    p_metric.add_argument("--model")
    p_metric.add_argument("--checkpoint", type=int)
    p_metric.add_argument("--force", action="store_true", help="Overwrite existing metric instead of skipping")
    p_metric.set_defaults(func=cmd_metric_log)

    # EXPORT
    p_export = subparsers.add_parser("export")
    p_export.add_argument("--db", required=True)
    p_export.add_argument("--output")
    p_export.set_defaults(func=cmd_export)

    # SCAN
    p_scan = subparsers.add_parser("scan", help="Auto-import eval results from a directory")
    p_scan.add_argument("--db", required=True)
    p_scan.add_argument("--run", required=True, help="Run name to register models under")
    p_scan.add_argument("--path", required=True, help="Root directory to scan")
    p_scan.add_argument("--format", default="lm_eval", choices=["lm_eval", "json"], help="Result format (default: lm_eval)")
    p_scan.add_argument("--prefix", help="Prefix to prepend to model names")
    p_scan.add_argument("--force", action="store_true", help="Overwrite existing metrics")
    p_scan.set_defaults(func=cmd_scan)

    # COMPARE
    p_cmp = subparsers.add_parser("compare", help="Compare metrics between two models")
    p_cmp.add_argument("--db", required=True)
    p_cmp.add_argument("--model-a", required=True, help="Baseline model name")
    p_cmp.add_argument("--model-b", required=True, help="Candidate model name")
    p_cmp.add_argument("--run", help="Filter to a specific run")
    p_cmp.add_argument("--family", help="Filter to a specific family")
    p_cmp.set_defaults(func=cmd_compare)

    # GUI
    p_gui = subparsers.add_parser("gui", help="Launch interactive dashboard (like tensorboard)")
    p_gui.add_argument("--db", required=True, help="Path to the LightML .db file")
    p_gui.add_argument("--port", type=int, default=5050, help="Port (default: 5050)")
    p_gui.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    p_gui.set_defaults(func=cmd_gui)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()