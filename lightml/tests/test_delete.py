"""Tests for model delete cascade logic."""

import tempfile
import sqlite3
import pytest
from pathlib import Path

from lightml.registry import initialize_registry, create_run
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle
from lightml.database import delete_model
from lightml.models.delete import DeleteResult


@pytest.fixture
def populated_registry():
    """Registry with a parent model, child model with checkpoints and metrics."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="del_test",
            overwrite=True,
            metrics_schema=[],
        )
        db_path = str(initialize_registry(registry))
        create_run(db=db_path, run_name="run1")

        h = LightMLHandle(db=db_path, run_name="run1")

        # Parent model
        parent_dir = Path(tmp) / "parent_model"
        parent_dir.mkdir()
        h.register_model(model_name="parent", path=str(parent_dir))
        h.log_model_metric("parent", "bench", "acc", 0.90)

        # Child model with checkpoints and metrics
        child_dir = Path(tmp) / "child_model"
        child_dir.mkdir()
        h.register_model(model_name="child", path=str(child_dir), parent_name="parent")

        h.register_checkpoint(model_name="child", step=100, path=str(child_dir / "ckpt100"))
        h.register_checkpoint(model_name="child", step=200, path=str(child_dir / "ckpt200"))

        # Model-level metrics
        h.log_model_metric("child", "eng", "hellaswag", 0.72)
        h.log_model_metric("child", "ita", "hellaswag", 0.65)

        # Checkpoint-level metrics
        with sqlite3.connect(db_path) as conn:
            ckpts = conn.execute(
                "SELECT id FROM checkpoint WHERE model_id = "
                "(SELECT id FROM model WHERE model_name='child')"
            ).fetchall()
        for ckpt_id in [c[0] for c in ckpts]:
            h.log_checkpoint_metric(ckpt_id, "eng", "hellaswag", 0.70)
            h.log_checkpoint_metric(ckpt_id, "ita", "hellaswag", 0.63)

        yield {
            "db_path": db_path,
            "tmp_dir": tmp,
            "handle": h,
        }


# ── Core delete tests ──


def test_delete_model_cascade(populated_registry):
    """Deleting a model removes its checkpoints and all metrics."""
    db = populated_registry["db_path"]

    result = delete_model(db=db, model_name="child")

    assert isinstance(result, DeleteResult)
    assert result.model_name == "child"
    assert result.checkpoints_deleted == 2
    assert result.metrics_deleted == 6  # 2 model-level + 4 checkpoint-level

    # Verify nothing remains in DB
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM model WHERE model_name='child'").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM checkpoint WHERE model_id NOT IN (SELECT id FROM model)"
        ).fetchone()[0] == 0


def test_delete_model_not_found(populated_registry):
    """Deleting a non-existent model raises ValueError."""
    db = populated_registry["db_path"]
    with pytest.raises(ValueError, match="not found"):
        delete_model(db=db, model_name="nonexistent")


def test_delete_parent_keeps_child(populated_registry):
    """Deleting parent sets child's parent_id to NULL (ON DELETE SET NULL)."""
    db = populated_registry["db_path"]

    delete_model(db=db, model_name="parent")

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT parent_id FROM model WHERE model_name='child'"
        ).fetchone()
        assert row is not None  # child still exists
        assert row[0] is None   # parent_id set to NULL


def test_delete_removes_symlink(populated_registry):
    """Deleting a model removes its symlink from registry/models/."""
    db = populated_registry["db_path"]
    tmp = populated_registry["tmp_dir"]

    # Symlink should exist after registration
    link = Path(tmp) / "models" / "child"
    assert link.is_symlink()

    delete_model(db=db, model_name="child")

    assert not link.exists()


def test_delete_model_no_metrics(populated_registry):
    """Model with no metrics/checkpoints can be deleted cleanly."""
    db = populated_registry["db_path"]
    h = populated_registry["handle"]
    tmp = populated_registry["tmp_dir"]

    bare_dir = Path(tmp) / "bare"
    bare_dir.mkdir()
    h.register_model(model_name="bare", path=str(bare_dir))

    result = delete_model(db=db, model_name="bare")
    assert result.checkpoints_deleted == 0
    assert result.metrics_deleted == 0


# ── Handle method test ──


def test_handle_delete_model(populated_registry):
    """Handle.delete_model delegates to core delete."""
    h = populated_registry["handle"]

    result = h.delete_model("child")

    assert result.model_name == "child"
    assert result.checkpoints_deleted == 2
    assert result.metrics_deleted == 6
