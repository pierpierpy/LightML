from lightml.registry import register_model, create_run
from lightml.checkpoints import register_checkpoint, find_checkpoint
from lightml.metrics import add_metric, METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED
from lightml.database import delete_model as _delete_model
from lightml.models.delete import DeleteResult
from lightml.readers import get_detailed_scores as _get_detailed_scores
from lightml.readers import get_detailed_scores_any_run as _get_detailed_scores_any_run
from lightml.readers import model_exists as _model_exists
from lightml.readers import metric_exists as _metric_exists
from lightml.readers import run_metric_exists as _run_metric_exists
from lightml.readers import search_entries as _search_entries
from lightml.stats import compare_models_stats


class LightMLHandle:

    def __init__(self, db: str, run_name: str | None = None):
        self.db = db
        self.run_name = run_name

        # auto-migrate schema for older databases
        from lightml.database import migrate_database
        migrate_database(self.db)

        # crea run se non esiste
        if self.run_name is not None:
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

    def find_checkpoint(self, model_name: str, step: int,
                        path_hint: str | None = None) -> int | None:
        """Look up a checkpoint id by model name and step.

        When multiple checkpoints share the same step (grid search),
        *path_hint* disambiguates by matching against the stored path.
        """
        return find_checkpoint(
            db=self.db,
            run_name=self.run_name,
            model_name=model_name,
            step=step,
            path_hint=path_hint,
        )

    # ------------------------
    # METRICS
    # ------------------------

    def log_model_metric(self, model_name: str, family: str, metric_name: str, value: float,scores: list[float] | None = None, *, force: bool = False):
        return add_metric(
            db=self.db,
            run_name=self.run_name,
            family=family,
            metric_name=metric_name,
            value=value,
            scores = scores, 
            model_name=model_name,
            force=force,
        )

    def log_checkpoint_metric(self, checkpoint_id: int, family: str, metric_name: str, value: float, scores: list[float] | None = None, *, force: bool = False):
        return add_metric(
            db=self.db,
            family=family,
            metric_name=metric_name,
            value=value,
            scores = scores,
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

    # ------------------------
    # DELETE
    # ------------------------

    def delete_model(self, model_name: str) -> DeleteResult:
        """Delete a model and all its checkpoints, metrics, and symlinks."""
        return _delete_model(db=self.db, model_name=model_name)

    # ------------------------
    # QUERIES
    # ------------------------

    def model_exists(self, model_name: str) -> bool:
        return _model_exists(self.db, model_name)

    def metric_exists(self, model_name: str, family: str, metric_name: str) -> bool:
        return _metric_exists(self.db, model_name, family, metric_name)

    def run_metric_exists(self, model_name: str,
                          family: str, metric_name: str) -> bool:
        return _run_metric_exists(self.db, self.run_name, model_name, family, metric_name)

    def search(self, model: str, family: str | None = None,
               metric: str | None = None) -> list[dict]:
        """Search models/metrics using exact match or glob patterns (* and ?)."""
        return _search_entries(self.db, model, family, metric, self.run_name)

    def get_detailed_scores(self, model_name, family, metric_name):
        return _get_detailed_scores(self.db, model_name, self.run_name, family, metric_name)

    def compare_stats(self, model_a, model_b, family, metric_name):
        scores_a = _get_detailed_scores_any_run(self.db, model_a, family, metric_name)
        scores_b = _get_detailed_scores_any_run(self.db, model_b, family, metric_name)
        return compare_models_stats(scores_a, scores_b)