import argparse
import sqlite3
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule


def load_from_db(db_path: Path):

    rows = []
    metrics_map = {}
    families = {}

    with sqlite3.connect(db_path) as conn:

        # MODELS
        model_rows = conn.execute("""
            SELECT m.id, m.model_name
            FROM model m
        """).fetchall()

        for mid, name in model_rows:
            rows.append({
                "key": ("model", mid),
                "name": name,
                "phase": "F"
            })

        # CHECKPOINTS
        ckpt_rows = conn.execute("""
            SELECT c.id, c.step, m.model_name
            FROM checkpoint c
            JOIN model m ON c.model_id = m.id
        """).fetchall()

        for cid, step, model_name in ckpt_rows:
            rows.append({
                "key": ("ckpt", cid),
                "name": f"{model_name}-STEP-{step}",
                "phase": "S"
            })

        # METRICS
        metric_rows = conn.execute("""
            SELECT model_id, checkpoint_id, family, metric_name, value
            FROM metrics
        """).fetchall()

        for model_id, checkpoint_id, family, metric_name, value in metric_rows:

            if model_id:
                key = ("model", model_id)
            elif checkpoint_id:
                key = ("ckpt", checkpoint_id)
            else:
                continue

            if family not in families:
                families[family] = set()

            families[family].add(metric_name)

            if key not in metrics_map:
                metrics_map[key] = {}

            if family not in metrics_map[key]:
                metrics_map[key][family] = {}

            metrics_map[key][family][metric_name] = value

    return rows, metrics_map, families


def export_excel(db_path: Path, output_path: Path):

    rows, metrics_map, families = load_from_db(db_path)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for family, metric_names in families.items():

        ws = wb.create_sheet(title=family)

        metric_names = sorted(metric_names)

        columns = ["Model", "Phase"] + metric_names

        # HEADER
        for col_idx, col in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")

        # DATA
        for row_idx, row in enumerate(rows, start=2):

            key = row["key"]
            family_metrics = metrics_map.get(key, {}).get(family, {})

            ws.cell(row=row_idx, column=1, value=row["name"])
            ws.cell(row=row_idx, column=2, value=row["phase"])

            for col_idx, metric in enumerate(metric_names, start=3):
                val = family_metrics.get(metric)
                ws.cell(row=row_idx, column=col_idx, value=val)

        # Conditional formatting
        max_row = ws.max_row

        for col_idx in range(3, len(columns) + 1):
            col_letter = get_column_letter(col_idx)

            ws.conditional_formatting.add(
                f"{col_letter}2:{col_letter}{max_row}",
                ColorScaleRule(
                    start_type='min', start_color='F8696B',
                    mid_type='percentile', mid_value=50, mid_color='FFEB84',
                    end_type='max', end_color='63BE7B'
                )
            )

        ws.freeze_panes = "B2"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)

    print(f"Export completed: {output_path}")


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output")

    args = parser.parse_args()

    db_path = Path(args.db)

    if args.output:
        output_path = Path(args.output)
    else:
        date = datetime.now().strftime("%Y-%m-%d")
        output_path = Path("report") / f"{db_path.stem}_report_{date}.xlsx"

    export_excel(db_path, output_path)


if __name__ == "__main__":
    main()