"""
Test suite for the compare feature.

Covers:
    - MetricDelta / CompareResult Pydantic models
    - compare_models() function with various filters
    - Edge cases: missing metrics, same model, non-existent model
"""

import tempfile
import pytest
from pathlib import Path

from lightml.compare import MetricDelta, CompareResult, compare_models
from lightml.registry import initialize_registry, create_run
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle


# ============================================================================
# UNIT: MetricDelta
# ============================================================================

class TestMetricDelta:
    """Validate the Pydantic MetricDelta model."""

    def test_delta_computed(self):
        d = MetricDelta(family="bench", metric_name="acc", value_a=0.80, value_b=0.85)
        assert d.delta == pytest.approx(0.05, abs=1e-4)
        assert d.pct_change == pytest.approx(6.25, abs=0.01)

    def test_delta_negative(self):
        d = MetricDelta(family="bench", metric_name="f1", value_a=0.75, value_b=0.70)
        assert d.delta == pytest.approx(-0.05, abs=1e-4)
        assert d.pct_change < 0

    def test_delta_zero_change(self):
        d = MetricDelta(family="bench", metric_name="x", value_a=0.5, value_b=0.5)
        assert d.delta == 0.0
        assert d.pct_change == 0.0

    def test_value_a_none(self):
        d = MetricDelta(family="bench", metric_name="x", value_a=None, value_b=0.5)
        assert d.delta is None
        assert d.pct_change is None

    def test_value_b_none(self):
        d = MetricDelta(family="bench", metric_name="x", value_a=0.5, value_b=None)
        assert d.delta is None
        assert d.pct_change is None

    def test_both_none(self):
        d = MetricDelta(family="bench", metric_name="x", value_a=None, value_b=None)
        assert d.delta is None
        assert d.pct_change is None

    def test_value_a_zero_no_pct(self):
        """% change is undefined when baseline is zero."""
        d = MetricDelta(family="bench", metric_name="x", value_a=0.0, value_b=1.0)
        assert d.delta == pytest.approx(1.0, abs=1e-4)
        assert d.pct_change is None  # division by zero avoided

    def test_serialisation(self):
        d = MetricDelta(family="f", metric_name="m", value_a=0.1, value_b=0.2)
        data = d.model_dump()
        assert "family" in data
        assert "delta" in data
        reconstructed = MetricDelta(**data)
        assert reconstructed.family == d.family


# ============================================================================
# UNIT: CompareResult
# ============================================================================

class TestCompareResult:
    """Validate CompareResult convenience methods."""

    def _make_result(self):
        deltas = [
            MetricDelta(family="a", metric_name="m1", value_a=0.5, value_b=0.6),   # improved
            MetricDelta(family="a", metric_name="m2", value_a=0.5, value_b=0.4),   # regressed
            MetricDelta(family="b", metric_name="m3", value_a=0.5, value_b=0.5),   # unchanged
            MetricDelta(family="b", metric_name="m4", value_a=0.5, value_b=None),  # missing
        ]
        return CompareResult(model_a="A", model_b="B", run_name="run1", deltas=deltas)

    def test_improved_count(self):
        r = self._make_result()
        assert len(r.improved) == 1
        assert r.improved[0].metric_name == "m1"

    def test_regressed_count(self):
        r = self._make_result()
        assert len(r.regressed) == 1
        assert r.regressed[0].metric_name == "m2"

    def test_unchanged_count(self):
        r = self._make_result()
        assert len(r.unchanged) == 1

    def test_missing_count(self):
        r = self._make_result()
        assert len(r.missing) == 1

    def test_to_dict_structure(self):
        r = self._make_result()
        d = r.to_dict()
        assert d["model_a"] == "A"
        assert d["model_b"] == "B"
        assert d["run"] == "run1"
        assert d["summary"]["improved"] == 1
        assert d["summary"]["regressed"] == 1
        assert d["summary"]["unchanged"] == 1
        assert d["summary"]["missing"] == 1
        assert len(d["deltas"]) == 4

    def test_to_text_contains_model_names(self):
        r = self._make_result()
        text = r.to_text(color=False)
        assert "A" in text
        assert "B" in text
        assert "improved" in text

    def test_empty_deltas(self):
        r = CompareResult(model_a="X", model_b="Y", run_name=None, deltas=[])
        assert len(r.improved) == 0
        assert len(r.regressed) == 0
        d = r.to_dict()
        assert d["summary"]["improved"] == 0


# ============================================================================
# INTEGRATION: compare_models()
# ============================================================================

class TestCompareModels:
    """Integration tests using a real SQLite DB."""

    def test_basic_compare(self, two_model_registry):
        db = two_model_registry["db_path"]
        result = compare_models(db, "model_a", "model_b", run_name="run1")

        assert result.model_a == "model_a"
        assert result.model_b == "model_b"
        assert len(result.deltas) == 2  # acc + f1
        # acc improved (0.80 → 0.85), f1 regressed (0.75 → 0.70)
        assert len(result.improved) == 1
        assert len(result.regressed) == 1

    def test_compare_with_family_filter(self, two_model_registry):
        db = two_model_registry["db_path"]
        result = compare_models(db, "model_a", "model_b", run_name="run1", family="bench")
        assert len(result.deltas) == 2

    def test_compare_nonexistent_family_empty(self, two_model_registry):
        db = two_model_registry["db_path"]
        result = compare_models(db, "model_a", "model_b", run_name="run1", family="nonexistent")
        assert len(result.deltas) == 0

    def test_compare_model_not_found(self, two_model_registry):
        db = two_model_registry["db_path"]
        with pytest.raises(ValueError, match="not found"):
            compare_models(db, "model_a", "DOES_NOT_EXIST", run_name="run1")

    def test_compare_no_run_matches_any(self, two_model_registry):
        """When run_name is None, compare across all runs."""
        db = two_model_registry["db_path"]
        result = compare_models(db, "model_a", "model_b")
        assert len(result.deltas) == 2

    def test_compare_same_model(self, two_model_registry):
        """Comparing a model to itself should yield zero deltas."""
        db = two_model_registry["db_path"]
        result = compare_models(db, "model_a", "model_a", run_name="run1")
        assert all(d.delta == 0 for d in result.deltas)

    def test_compare_partial_metrics(self):
        """Model B has extra metrics that A doesn't, and vice versa."""
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistryInit(
                registry_path=tmp, registry_name="partial", overwrite=True, metrics_schema=[]
            )
            db = str(initialize_registry(reg))
            create_run(db=db, run_name="r1")

            h = LightMLHandle(db=db, run_name="r1")
            h.register_model(model_name="alpha", path=tmp)
            h.register_model(model_name="beta", path=tmp)

            h.log_model_metric("alpha", "fam", "shared", 0.5)
            h.log_model_metric("alpha", "fam", "only_a", 0.3)

            h.log_model_metric("beta", "fam", "shared", 0.6)
            h.log_model_metric("beta", "fam", "only_b", 0.9)

            result = compare_models(db, "alpha", "beta", run_name="r1")
            assert len(result.deltas) == 3  # shared, only_a, only_b
            assert len(result.missing) == 2  # only_a, only_b
            assert len(result.improved) == 1  # shared
