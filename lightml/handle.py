from lightml.registry import register_model
from lightml.checkpoints import register_checkpoint
from lightml.metrics import add_metric


class LightMLHandle:

    def __init__(self, db: str):
        self.db = db

    def register_model(self, model_name: str, path: str, parent_name: str | None = None):
        return register_model(
            model_name=model_name,
            path=path,
            db=self.db,
            parent_name=parent_name,
        )

    def register_checkpoint(self, model_name: str, step: int, path: str):
        return register_checkpoint(
            db=self.db,
            model_name=model_name,
            step=step,
            path=path,
        )

    def log_model_metric(self, model_name: str, family: str, metric_name: str, value: float):
        return add_metric(
            db=self.db,
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