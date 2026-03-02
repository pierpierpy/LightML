import argparse
from pathlib import Path

from lightml.handle import LightMLHandle
from lightml.export import export_excel
from lightml.registry import initialize_registry
from lightml.models.registry import RegistryInit


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


def cmd_gui(args):
    from lightml.gui import launch
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