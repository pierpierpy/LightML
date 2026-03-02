"""
Test suite for the scan / auto-import feature.

Covers:
    - _parse_lm_eval() format adapter
    - _parse_json() format adapter (nested + flat)
    - scan_and_import() integration
    - Edge cases: empty dirs, bad JSON, unknown format
"""

import json
import tempfile
import pytest
from pathlib import Path

from lightml.scan import _parse_lm_eval, _parse_json, scan_and_import, ScanStats
from lightml.registry import initialize_registry, create_run
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle


# ============================================================================
# HELPERS
# ============================================================================

def _make_lm_eval_dir(parent: Path, model_name: str, results: dict) -> Path:
    """Create a fake lm-eval result directory."""
    d = parent / model_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "results_2026-01-01T00-00-00.json").write_text(
        json.dumps({"results": results})
    )
    return d


def _make_flat_json_dir(parent: Path, model_name: str, metrics: dict) -> Path:
    """Create a directory with a flat metrics.json."""
    d = parent / model_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "metrics.json").write_text(json.dumps(metrics))
    return d


def _make_nested_json_dir(parent: Path, model_name: str, nested: dict) -> Path:
    """Create a directory with a nested metrics.json."""
    d = parent / model_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "metrics.json").write_text(json.dumps(nested))
    return d


# ============================================================================
# UNIT: _parse_lm_eval
# ============================================================================

class TestParseLmEval:
    """Tests for the lm-eval format adapter."""

    def test_standard_results(self, tmp_path):
        d = _make_lm_eval_dir(tmp_path, "model1", {
            "mmlu": {"acc": 0.56, "acc_stderr": 0.01, "alias": "mmlu"},
            "hellaswag": {"acc_norm": 0.72, "acc_norm_stderr": 0.005},
        })
        result = _parse_lm_eval(d)
        assert result is not None
        assert "mmlu" in result
        assert "hellaswag" in result
        assert "acc" in result["mmlu"]
        assert "acc_norm" in result["hellaswag"]
        # alias key should be excluded (non-numeric)
        assert "alias" not in result["mmlu"]

    def test_comma_suffix_cleaned(self, tmp_path):
        """lm_eval sometimes appends ',none' to metric keys."""
        d = _make_lm_eval_dir(tmp_path, "model2", {
            "arc": {"acc,none": 0.48, "acc_norm,none": 0.52},
        })
        result = _parse_lm_eval(d)
        assert result is not None
        assert "acc" in result["arc"]
        assert "acc_norm" in result["arc"]
        assert "acc,none" not in result["arc"]

    def test_empty_results(self, tmp_path):
        d = _make_lm_eval_dir(tmp_path, "empty", {})
        result = _parse_lm_eval(d)
        assert result is None

    def test_no_json_files(self, tmp_path):
        d = tmp_path / "no_json"
        d.mkdir()
        result = _parse_lm_eval(d)
        assert result is None

    def test_bad_json(self, tmp_path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "results_2026-01-01T00-00-00.json").write_text("{broken json")
        result = _parse_lm_eval(d)
        assert result is None

    def test_picks_latest_file(self, tmp_path):
        d = tmp_path / "multi"
        d.mkdir()
        # Older file with different values
        (d / "results_2025-01-01T00-00-00.json").write_text(
            json.dumps({"results": {"task": {"old_metric": 0.1}}})
        )
        # Newer file
        (d / "results_2026-06-15T12-00-00.json").write_text(
            json.dumps({"results": {"task": {"new_metric": 0.9}}})
        )
        result = _parse_lm_eval(d)
        assert result is not None
        assert "new_metric" in result["task"]


# ============================================================================
# UNIT: _parse_json
# ============================================================================

class TestParseJson:
    """Tests for the generic JSON format adapter."""

    def test_nested_format(self, tmp_path):
        d = _make_nested_json_dir(tmp_path, "nested", {
            "family_a": {"m1": 0.5, "m2": 0.6},
            "family_b": {"m3": 0.7},
        })
        result = _parse_json(d)
        assert result is not None
        assert "family_a" in result
        assert result["family_a"]["m1"] == 0.5

    def test_flat_format(self, tmp_path):
        d = _make_flat_json_dir(tmp_path, "flat", {
            "accuracy": 0.9,
            "f1": 0.85,
        })
        result = _parse_json(d)
        assert result is not None
        # Flat uses filename stem as family
        assert "metrics" in result
        assert result["metrics"]["accuracy"] == 0.9

    def test_no_files(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        result = _parse_json(d)
        assert result is None

    def test_non_numeric_values_skipped(self, tmp_path):
        d = _make_flat_json_dir(tmp_path, "mixed", {
            "score": 0.8,
            "name": "some_string",
            "ok": True,
        })
        result = _parse_json(d)
        assert result is not None
        family = list(result.keys())[0]
        assert "score" in result[family]
        assert "name" not in result[family]


# ============================================================================
# INTEGRATION: scan_and_import
# ============================================================================

class TestScanAndImport:
    """Integration tests with a real DB and temp directories."""

    def _setup_db(self, tmp_dir: str) -> str:
        reg = RegistryInit(
            registry_path=tmp_dir,
            registry_name="scan_test",
            overwrite=True,
            metrics_schema=[],
        )
        db = str(initialize_registry(reg))
        create_run(db=db, run_name="scan-run")
        return db

    def test_scan_lm_eval(self, tmp_path):
        # Create eval results tree
        root = tmp_path / "results"
        root.mkdir()
        _make_lm_eval_dir(root, "model_x", {
            "mmlu": {"acc": 0.56, "acc_stderr": 0.01},
        })
        _make_lm_eval_dir(root, "model_y", {
            "hellaswag": {"acc_norm": 0.72},
        })

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        stats = scan_and_import(db, "scan-run", str(root), format="lm_eval")
        assert isinstance(stats, ScanStats)
        assert stats.models_registered == 2
        assert stats.metrics_logged >= 2  # at least one metric per model

    def test_scan_json(self, tmp_path):
        root = tmp_path / "results"
        root.mkdir()
        _make_nested_json_dir(root, "my_model", {
            "bench": {"acc": 0.9, "f1": 0.8},
        })

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        stats = scan_and_import(db, "scan-run", str(root), format="json")
        assert stats.models_registered == 1
        assert stats.metrics_logged == 2

    def test_scan_unknown_format(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        with pytest.raises(ValueError, match="Unknown format"):
            scan_and_import(db, "scan-run", str(tmp_path), format="csv")

    def test_scan_nonexistent_directory(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        with pytest.raises(FileNotFoundError):
            scan_and_import(db, "scan-run", str(tmp_path / "nope"))

    def test_scan_skips_empty_dirs(self, tmp_path):
        root = tmp_path / "results"
        root.mkdir()
        (root / "empty_model").mkdir()  # no JSON inside

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        stats = scan_and_import(db, "scan-run", str(root))
        assert stats.models_registered == 0
        assert "empty_model" in stats.skipped_dirs

    def test_scan_with_prefix(self, tmp_path):
        root = tmp_path / "results"
        root.mkdir()
        _make_lm_eval_dir(root, "my_model", {
            "task": {"acc": 0.5},
        })

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        stats = scan_and_import(
            db, "scan-run", str(root), format="lm_eval", model_prefix="prefix/"
        )
        assert stats.models_registered == 1

        # Verify the model was registered with the prefix
        import sqlite3
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT model_name FROM model WHERE model_name = ?",
                ("prefix/my_model",),
            ).fetchone()
            assert row is not None

    def test_scan_force_updates(self, tmp_path):
        root = tmp_path / "results"
        root.mkdir()
        _make_lm_eval_dir(root, "model_z", {
            "task": {"acc": 0.5},
        })

        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db = self._setup_db(str(db_dir))

        # First scan
        s1 = scan_and_import(db, "scan-run", str(root), format="lm_eval")
        assert s1.metrics_logged >= 1

        # Second scan without force — should skip
        s2 = scan_and_import(db, "scan-run", str(root), format="lm_eval")
        assert s2.metrics_logged == 0  # all skipped (dedup)

        # Third scan with force — should update
        s3 = scan_and_import(db, "scan-run", str(root), format="lm_eval", force=True)
        assert s3.metrics_logged >= 1
