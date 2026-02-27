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
    handle = LightMLHandle(
        db=args.db,
        run_name=args.run
    )

    if args.checkpoint:
        handle.log_checkpoint_metric(
            checkpoint_id=args.checkpoint,
            family=args.family,
            metric_name=args.metric,
            value=args.value,
        )
    else:
        handle.log_model_metric(
            model_name=args.model,
            family=args.family,
            metric_name=args.metric,
            value=args.value,
        )

    print("Metric logged.")


def cmd_export(args):
    db_path = Path(args.db)

    if args.output:
        output = Path(args.output)
    else:
        output = Path("report") / f"{db_path.stem}_report.xlsx"

    export_excel(db_path, output)


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
    p_metric.set_defaults(func=cmd_metric_log)

    # EXPORT
    p_export = subparsers.add_parser("export")
    p_export.add_argument("--db", required=True)
    p_export.add_argument("--output")
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()