"""
Test suite for the bulk metric logging API.

Covers:
    - log_metrics() — nested dict {family: {metric: value}}
    - log_metrics_flat() — flat dict with explicit family
    - Deduplication + force behaviour
    - Return value counts
"""

import tempfile
import pytest
from pathlib import Path

from lightml.registry import initialize_registry, create_run
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle
from lightml.metrics import METRIC_INSERTED, METRIC_UPDATED, METRIC_SKIPPED


# ============================================================================
# UNIT: log_metrics
# ============================================================================

class TestLogMetrics:
    """Tests for LightMLHandle.log_metrics()."""

    def test_insert_counts(self, fresh_registry):
        h = fresh_registry["handle"]
        result = h.log_metrics("model_a", {
            "family1": {"m1": 0.5, "m2": 0.6},
            "family2": {"m3": 0.7},
        })
        assert result["inserted"] == 3
        assert result["updated"] == 0
        assert result["skipped"] == 0

    def test_empty_dict(self, fresh_registry):
        h = fresh_registry["handle"]
        result = h.log_metrics("model_a", {})
        assert result == {"inserted": 0, "updated": 0, "skipped": 0}

    def test_empty_family(self, fresh_registry):
        h = fresh_registry["handle"]
        result = h.log_metrics("model_a", {"empty_fam": {}})
        assert result["inserted"] == 0

    def test_dedup_skip(self, fresh_registry):
        h = fresh_registry["handle"]
        h.log_metrics("model_a", {"f": {"m": 0.5}})
        result = h.log_metrics("model_a", {"f": {"m": 0.5}})
        assert result["skipped"] == 1
        assert result["inserted"] == 0

    def test_dedup_force_update(self, fresh_registry):
        h = fresh_registry["handle"]
        h.log_metrics("model_a", {"f": {"m": 0.5}})
        result = h.log_metrics("model_a", {"f": {"m": 0.9}}, force=True)
        assert result["updated"] == 1
        assert result["inserted"] == 0

    def test_multiple_families(self, fresh_registry):
        h = fresh_registry["handle"]
        result = h.log_metrics("model_a", {
            "accuracy": {"test_acc": 0.95, "val_acc": 0.93},
            "loss": {"train_loss": 0.12, "val_loss": 0.15},
            "timing": {"inference_ms": 42.5},
        })
        assert result["inserted"] == 5

    def test_values_persisted(self, fresh_registry):
        """Verify metrics are actually in the DB after bulk insert."""
        import sqlite3

        h = fresh_registry["handle"]
        db = fresh_registry["db_path"]

        h.log_metrics("model_a", {
            "bench": {"acc": 0.88, "f1": 0.82},
        })

        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT metric_name, value FROM metrics WHERE family = 'bench'"
            ).fetchall()

        metrics = {r[0]: r[1] for r in rows}
        assert metrics["acc"] == pytest.approx(0.88)
        assert metrics["f1"] == pytest.approx(0.82)


# ============================================================================
# UNIT: log_metrics_flat
# ============================================================================

class TestLogMetricsFlat:
    """Tests for LightMLHandle.log_metrics_flat()."""

    def test_basic_flat(self, fresh_registry):
        h = fresh_registry["handle"]
        result = h.log_metrics_flat("model_a", {"acc": 0.9, "f1": 0.85}, family="bench")
        assert result["inserted"] == 2

    def test_flat_dedup(self, fresh_registry):
        h = fresh_registry["handle"]
        h.log_metrics_flat("model_a", {"x": 0.5}, family="f1")
        result = h.log_metrics_flat("model_a", {"x": 0.5}, family="f1")
        assert result["skipped"] == 1

    def test_flat_force(self, fresh_registry):
        h = fresh_registry["handle"]
        h.log_metrics_flat("model_a", {"x": 0.5}, family="f1")
        result = h.log_metrics_flat("model_a", {"x": 0.9}, family="f1", force=True)
        assert result["updated"] == 1

    def test_flat_empty(self, fresh_registry):
        h = fresh_registry["handle"]
        result = h.log_metrics_flat("model_a", {}, family="f1")
        assert result["inserted"] == 0


# ============================================================================
# INTEGRATION: mixed usage
# ============================================================================

class TestBulkIntegration:
    """Cross-cutting tests for the bulk API with other features."""

    def test_bulk_then_compare(self):
        """Metrics logged via bulk API are visible to compare_models."""
        from lightml.compare import compare_models

        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistryInit(
                registry_path=tmp, registry_name="bulk_cmp", overwrite=True, metrics_schema=[]
            )
            db = str(initialize_registry(reg))
            create_run(db=db, run_name="r1")

            h = LightMLHandle(db=db, run_name="r1")
            import os
            pb = os.path.join(tmp, "base"); os.makedirs(pb)
            pt = os.path.join(tmp, "tuned"); os.makedirs(pt)
            h.register_model(model_name="base", path=pb)
            h.register_model(model_name="tuned", path=pt)

            h.log_metrics("base", {"bench": {"acc": 0.5, "f1": 0.4}})
            h.log_metrics("tuned", {"bench": {"acc": 0.7, "f1": 0.6}})

            result = compare_models(db, "base", "tuned", run_name="r1")
            assert len(result.improved) == 2  # both metrics improved

    def test_model_not_found(self, fresh_registry):
        """Logging metrics to a non-existent model raises ValueError."""
        h = fresh_registry["handle"]
        with pytest.raises(ValueError, match="not found"):
            h.log_metrics("NONEXISTENT", {"f": {"m": 0.5}})

    def test_checkpoint_metrics_separate(self, fresh_registry):
        """Checkpoint metrics logged individually don't interfere with model metrics."""
        h = fresh_registry["handle"]
        h.log_metrics("model_a", {"bench": {"acc": 0.8}})

        ckpt_id = h.register_checkpoint(model_name="model_a", step=100, path="/tmp/ckpt")
        h.log_checkpoint_metric(ckpt_id, "bench", "acc", 0.75)

        import sqlite3
        with sqlite3.connect(fresh_registry["db_path"]) as conn:
            model_rows = conn.execute(
                "SELECT value FROM metrics WHERE model_id IS NOT NULL AND metric_name = 'acc'"
            ).fetchall()
            ckpt_rows = conn.execute(
                "SELECT value FROM metrics WHERE checkpoint_id IS NOT NULL AND metric_name = 'acc'"
            ).fetchall()

        assert len(model_rows) == 1
        assert model_rows[0][0] == pytest.approx(0.8)
        assert len(ckpt_rows) == 1
        assert ckpt_rows[0][0] == pytest.approx(0.75)
