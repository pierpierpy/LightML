from lightml.registry import register_model, create_run
from lightml.checkpoints import register_checkpoint
from lightml.metrics import add_metric


class LightMLHandle:

    def __init__(self, db: str, run_name: str):
        self.db = db
        self.run_name = run_name

        # crea run se non esiste
        create_run(
            db=self.db,
            run_name=self.run_name
        )

    # ------------------------
    # MODEL
    # ------------------------

    def register_model(self, model_name: str, path: str, parent_name: str | None = None):
        return register_model(
            db=self.db,
            run_name=self.run_name,
            model_name=model_name,
            path=path,
            parent_name=parent_name,
        )

    # ------------------------
    # CHECKPOINT
    # ------------------------

    def register_checkpoint(self, model_name: str, step: int, path: str):
        return register_checkpoint(
            db=self.db,
            run_name=self.run_name,
            model_name=model_name,
            step=step,
            path=path,
        )

    # ------------------------
    # METRICS
    # ------------------------

    def log_model_metric(self, model_name: str, family: str, metric_name: str, value: float):
        return add_metric(
            db=self.db,
            run_name=self.run_name,
            family=family,
            metric_name=metric_name,
            value=value,
            model_name=model_name,
        )

    def log_checkpoint_metric(self, checkpoint_id: int, family: str, metric_name: str, value: float):
        return add_metric(
            db=self.db,
            family=family,
            metric_name=metric_name,
            value=value,
            checkpoint_id=checkpoint_id,
        )