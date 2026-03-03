from lightml.registry import register_model, create_run
from lightml.checkpoints import register_checkpoint
from lightml.metrics import add_metric, METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED


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

    def register_model(self, model_name: str, path: str,
                       parent_name: str | None = None,
                       parent_id: int | None = None):
        return register_model(
            db=self.db,
            run_name=self.run_name,
            model_name=model_name,
            path=path,
            parent_name=parent_name,
            parent_id=parent_id,
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

    def log_model_metric(self, model_name: str, family: str, metric_name: str, value: float, *, force: bool = False):
        return add_metric(
            db=self.db,
            run_name=self.run_name,
            family=family,
            metric_name=metric_name,
            value=value,
            model_name=model_name,
            force=force,
        )

    def log_checkpoint_metric(self, checkpoint_id: int, family: str, metric_name: str, value: float, *, force: bool = False):
        return add_metric(
            db=self.db,
            family=family,
            metric_name=metric_name,
            value=value,
            checkpoint_id=checkpoint_id,
            force=force,
        )

    # ------------------------
    # BULK METRICS
    # ------------------------

    def log_metrics(
        self,
        model_name: str,
        metrics: dict[str, dict[str, float]],
        *,
        force: bool = False,
    ) -> dict[str, int]:
        """Log multiple metrics in one call.

        Args:
            model_name: Target model.
            metrics: ``{family: {metric_name: value, ...}, ...}``
            force: Overwrite existing metrics instead of skipping.

        Returns:
            ``{"inserted": N, "updated": N, "skipped": N}``
        """
        counts = {"inserted": 0, "updated": 0, "skipped": 0}
        for family, family_metrics in metrics.items():
            for metric_name, value in family_metrics.items():
                result = self.log_model_metric(
                    model_name=model_name,
                    family=family,
                    metric_name=metric_name,
                    value=value,
                    force=force,
                )
                if result == METRIC_INSERTED:
                    counts["inserted"] += 1
                elif result == METRIC_UPDATED:
                    counts["updated"] += 1
                elif result == METRIC_SKIPPED:
                    counts["skipped"] += 1
        return counts

    def log_metrics_flat(
        self,
        model_name: str,
        metrics: dict[str, float],
        family: str,
        *,
        force: bool = False,
    ) -> dict[str, int]:
        """Log metrics for a single family.

        Args:
            model_name: Target model.
            metrics: ``{metric_name: value, ...}``
            family: The benchmark family these metrics belong to.
            force: Overwrite existing metrics instead of skipping.

        Returns:
            ``{"inserted": N, "updated": N, "skipped": N}``
        """
        return self.log_metrics(
            model_name=model_name,
            metrics={family: metrics},
            force=force,
        )