"""Tests for lightml diff — side-by-side N-model comparison."""

import tempfile
from pathlib import Path

import pytest

from lightml.registry import initialize_registry, create_run
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle
from lightml.diff import diff_models, format_diff


@pytest.fixture
def three_model_registry():
    """Registry with three models for diff tests.

    model_a: bench/acc=0.80, bench/f1=0.75, mmlu/accuracy=0.65
    model_b: bench/acc=0.85, bench/f1=0.70, mmlu/accuracy=0.70
    model_c: bench/acc=0.79, bench/f1=0.78, mmlu/accuracy=0.72
    """
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="diff_registry",
            overwrite=True,
            metrics_schema=[],
        )
        db_path = str(initialize_registry(registry))
        create_run(db=db_path, run_name="run1")

        h = LightMLHandle(db=db_path, run_name="run1")
        for name in ("model_a", "model_b", "model_c"):
            p = Path(tmp) / name
            p.mkdir()
            h.register_model(model_name=name, path=str(p))

        h.log_model_metric("model_a", "bench", "acc", 0.80)
        h.log_model_metric("model_a", "bench", "f1", 0.75)
        h.log_model_metric("model_a", "mmlu", "accuracy", 0.65)

        h.log_model_metric("model_b", "bench", "acc", 0.85)
        h.log_model_metric("model_b", "bench", "f1", 0.70)
        h.log_model_metric("model_b", "mmlu", "accuracy", 0.70)

        h.log_model_metric("model_c", "bench", "acc", 0.79)
        h.log_model_metric("model_c", "bench", "f1", 0.78)
        h.log_model_metric("model_c", "mmlu", "accuracy", 0.72)

        yield {"db_path": db_path, "tmp_dir": tmp, "handle": h}


class TestDiffModels:
    """Test the diff_models() core function."""

    def test_basic_diff(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b", "model_c"],
        )
        assert data["models"] == ["model_a", "model_b", "model_c"]
        assert len(data["rows"]) == 3  # acc, f1, accuracy

    def test_diff_two_models(self, two_model_registry):
        data = diff_models(
            db=two_model_registry["db_path"],
            model_names=["model_a", "model_b"],
        )
        assert len(data["models"]) == 2
        assert len(data["rows"]) == 2  # acc, f1

    def test_diff_with_run_filter(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
            run_name="run1",
        )
        assert data["run_name"] == "run1"
        assert len(data["rows"]) == 3

    def test_diff_with_family_filter(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b", "model_c"],
            family="bench",
        )
        assert len(data["rows"]) == 2  # only acc and f1
        for row in data["rows"]:
            assert row["family"] == "bench"

    def test_diff_values_correct(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
            family="bench",
        )
        acc_row = next(r for r in data["rows"] if r["metric"] == "acc")
        assert acc_row["values"]["model_a"] == pytest.approx(0.80)
        assert acc_row["values"]["model_b"] == pytest.approx(0.85)

    def test_diff_missing_model_raises(self, three_model_registry):
        with pytest.raises(ValueError, match="not found"):
            diff_models(
                db=three_model_registry["db_path"],
                model_names=["model_a", "nonexistent"],
            )

    def test_diff_needs_at_least_two(self, three_model_registry):
        with pytest.raises(ValueError, match="at least 2"):
            diff_models(
                db=three_model_registry["db_path"],
                model_names=["model_a"],
            )

    def test_diff_partial_metrics(self, three_model_registry):
        """Model with a metric the others don't have → None for missing."""
        h = three_model_registry["handle"]
        h.log_model_metric("model_a", "extra", "special", 0.99)

        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
        )
        extra_row = next(r for r in data["rows"] if r["metric"] == "special")
        assert extra_row["values"]["model_a"] == pytest.approx(0.99)
        assert extra_row["values"]["model_b"] is None


class TestFormatDiff:
    """Test the terminal formatting."""

    def test_format_contains_model_names(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b", "model_c"],
        )
        output = format_diff(data, color=False)
        assert "model_a" in output
        assert "model_b" in output
        assert "model_c" in output

    def test_format_contains_metrics(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
        )
        output = format_diff(data, color=False)
        assert "acc" in output
        assert "f1" in output
        assert "accuracy" in output

    def test_format_contains_values(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
        )
        output = format_diff(data, color=False)
        assert "0.8000" in output
        assert "0.8500" in output

    def test_format_shows_avg(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b", "model_c"],
        )
        output = format_diff(data, color=False)
        assert "AVG" in output

    def test_format_no_color(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
        )
        output = format_diff(data, color=False)
        assert "\033[" not in output

    def test_format_with_color(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b", "model_c"],
        )
        output = format_diff(data, color=True)
        assert "\033[32m" in output  # green for best

    def test_format_empty_result(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
            family="nonexistent",
        )
        output = format_diff(data, color=False)
        assert "No metrics found" in output

    def test_format_shows_run_name(self, three_model_registry):
        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
            run_name="run1",
        )
        output = format_diff(data, color=False)
        assert "run1" in output

    def test_format_shows_dash_for_missing(self, three_model_registry):
        h = three_model_registry["handle"]
        h.log_model_metric("model_a", "extra", "only_a", 0.99)

        data = diff_models(
            db=three_model_registry["db_path"],
            model_names=["model_a", "model_b"],
        )
        output = format_diff(data, color=False)
        assert "—" in output
