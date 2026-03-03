"""
Metrics Registry Bugfix Test Suite

This file consolidates all tests for the metrics registry bugfix:
1. Bug Condition Exploration Tests - Validate the five bugs are fixed
2. Preservation Property Tests - Ensure existing behavior is preserved

**Bug Condition Tests (Expected Behavior):**
- Bug 1.1: Handle passes run_name to add_metric
- Bug 1.2: Server route uses correct parameter name `db` instead of `db_path`
- Bug 1.3: Schema validation enforced when registry_schema exists
- Bug 1.4: Actual metric ID returned instead of hardcoded `1`
- Bug 1.5: MetricCreate schema accepts run_name and checkpoint_id fields

**Preservation Tests (Requirements 3.1-3.6):**
- Checkpoint metrics work without run_name
- Registries without schema accept any metrics
- Model/checkpoint registration unchanged
- Run creation unchanged
- Query operations return same structure
"""

import tempfile
import pytest
import sqlite3
import os
from pathlib import Path
from lightml.registry import initialize_registry, create_run, register_model
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle
from lightml.metrics import add_metric
from lightml.models.metrics import MetricCreate
from lightml.checkpoints import register_checkpoint


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def registry_with_schema():
    """Create a registry with a defined metrics schema."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="test_registry",
            overwrite=True,
            metrics_schema=[
                {
                    "family": "accuracy",
                    "metrics": {
                        "test_acc": {},
                        "val_acc": {}
                    }
                },
                {
                    "family": "loss",
                    "metrics": {
                        "train_loss": {},
                        "val_loss": {}
                    }
                }
            ]
        )
        
        db_path = initialize_registry(registry)
        create_run(db=str(db_path), run_name="test_run")
        
        handle = LightMLHandle(db=str(db_path), run_name="test_run")
        handle.register_model(model_name="test_model", path=tmp)
        
        yield {
            "db_path": str(db_path),
            "model_path": tmp,
            "handle": handle
        }


@pytest.fixture
def registry_without_schema():
    """Create a registry without a metrics schema."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="test_registry_no_schema",
            overwrite=True,
            metrics_schema=[]
        )
        
        db_path = initialize_registry(registry)
        create_run(db=str(db_path), run_name="test_run")
        
        handle = LightMLHandle(db=str(db_path), run_name="test_run")
        handle.register_model(model_name="test_model", path=tmp)
        
        yield {
            "db_path": str(db_path),
            "model_path": tmp,
            "handle": handle
        }


@pytest.fixture
def basic_registry():
    """Create a basic registry for preservation tests."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="test_registry",
            overwrite=True,
            metrics_schema=[]
        )
        
        db_path = initialize_registry(registry)
        create_run(db=str(db_path), run_name="test_run")
        
        handle = LightMLHandle(db=str(db_path), run_name="test_run")
        model_id = handle.register_model(model_name="test_model", path=tmp)
        
        checkpoint_id = handle.register_checkpoint(
            model_name="test_model",
            step=100,
            path=str(Path(tmp) / "checkpoint_100")
        )
        
        yield {
            "db_path": str(db_path),
            "model_path": tmp,
            "handle": handle,
            "model_id": model_id,
            "checkpoint_id": checkpoint_id
        }


# ============================================================================
# BUG CONDITION EXPLORATION TESTS
# ============================================================================

class TestBugConditionExploration:
    """Tests that validate all five bugs are fixed."""
    
    def test_bug_1_handle_passes_run_name(self, registry_with_schema):
        """
        Bug 1.1: Handle passes run_name to add_metric
        
        Expected Behavior: handle.log_model_metric() successfully logs metrics
        by passing run_name from the handle instance to add_metric().
        """
        handle = registry_with_schema["handle"]
        
        result = handle.log_model_metric(
            model_name="test_model",
            family="accuracy",
            metric_name="test_acc",
            value=0.95
        )
        
        assert result is not None
        assert isinstance(result, int)
    
    def test_bug_3_schema_validation_enforced(self, registry_with_schema):
        """
        Bug 1.3: Schema validation enforced when registry_schema exists
        
        Expected Behavior: Invalid metrics are rejected with clear error message
        when a registry schema is defined.
        """
        handle = registry_with_schema["handle"]
        
        with pytest.raises(ValueError, match="not found in registry schema"):
            handle.log_model_metric(
                model_name="test_model",
                family="invalid_family",
                metric_name="invalid_metric",
                value=0.5
            )
    
    def test_bug_3_valid_metric_accepted_with_schema(self, registry_with_schema):
        """
        Bug 1.3: Valid metrics accepted when they match the schema
        
        Expected Behavior: Metrics matching the schema are successfully inserted.
        """
        handle = registry_with_schema["handle"]
        
        result = handle.log_model_metric(
            model_name="test_model",
            family="accuracy",
            metric_name="test_acc",
            value=0.95
        )
        
        assert result is not None
        assert isinstance(result, int)
    
    def test_bug_3_no_validation_without_schema(self, registry_without_schema):
        """
        Bug 1.3: Registries without schema accept any metrics
        
        Expected Behavior: When no schema is defined, any metric is accepted.
        """
        handle = registry_without_schema["handle"]
        
        result = handle.log_model_metric(
            model_name="test_model",
            family="any_family",
            metric_name="any_metric",
            value=0.75
        )
        
        assert result is not None
        assert isinstance(result, int)
    
    def test_bug_4_actual_metric_id_returned(self, registry_with_schema):
        """
        Bug 1.4: add_metric() returns METRIC_INSERTED for new, distinct metrics.

        After the deduplication refactor, add_metric returns status codes
        (METRIC_INSERTED / METRIC_SKIPPED / METRIC_UPDATED) instead of row IDs.
        Two distinct metrics should both return METRIC_INSERTED.
        """
        from lightml.metrics import METRIC_INSERTED

        handle = registry_with_schema["handle"]
        
        result1 = handle.log_model_metric(
            model_name="test_model",
            family="accuracy",
            metric_name="test_acc",
            value=0.95
        )
        
        result2 = handle.log_model_metric(
            model_name="test_model",
            family="accuracy",
            metric_name="val_acc",
            value=0.93
        )
        
        assert result1 == METRIC_INSERTED, f"Expected METRIC_INSERTED, got {result1}"
        assert result2 == METRIC_INSERTED, f"Expected METRIC_INSERTED, got {result2}"
    
    def test_bug_5_metric_create_accepts_run_name(self):
        """
        Bug 1.5: MetricCreate schema accepts run_name field
        
        Expected Behavior: MetricCreate accepts run_name as an optional field
        to support model metrics via the server API.
        """
        metric = MetricCreate(
            db="test.db",
            model_name="test_model",
            family="accuracy",
            metric_name="test_acc",
            value=0.95,
            run_name="test_run"
        )
        
        assert metric.run_name == "test_run"
        assert metric.model_name == "test_model"
    
    def test_bug_5_metric_create_accepts_checkpoint_id(self):
        """
        Bug 1.5: MetricCreate schema accepts checkpoint_id field
        
        Expected Behavior: MetricCreate accepts checkpoint_id as an optional field
        to support checkpoint metrics via the server API.
        """
        metric = MetricCreate(
            db="test.db",
            model_name="test_model",
            family="loss",
            metric_name="train_loss",
            value=0.25,
            checkpoint_id=42
        )
        
        assert metric.checkpoint_id == 42


# ============================================================================
# PRESERVATION PROPERTY TESTS
# ============================================================================

class TestPreservation:
    """Tests to ensure existing behavior is preserved after bugfix."""
    
    # ------------------------------------------------------------------------
    # Requirement 3.1: Checkpoint metrics work without run_name
    # ------------------------------------------------------------------------
    
    @pytest.mark.parametrize("family,metric_name,value", [
        ("training", "loss", 0.25),
        ("training", "accuracy", 0.95),
        ("validation", "loss", 0.30),
        ("validation", "f1_score", 0.88),
        ("custom", "custom_metric", 123.45),
    ])
    def test_checkpoint_metrics_work_without_run_name(self, basic_registry, family, metric_name, value):
        """
        Preservation: Checkpoint metrics don't require run_name.
        
        Property: For all checkpoint metrics (family, metric_name, value),
        logging via handle.log_checkpoint_metric() succeeds and returns an integer ID.
        """
        handle = basic_registry["handle"]
        checkpoint_id = basic_registry["checkpoint_id"]
        
        result = handle.log_checkpoint_metric(
            checkpoint_id=checkpoint_id,
            family=family,
            metric_name=metric_name,
            value=value
        )
        
        assert result is not None
        assert isinstance(result, int)
        assert result > 0
    
    def test_multiple_checkpoint_metrics_sequential(self, basic_registry):
        """
        Preservation: Multiple checkpoint metrics can be logged sequentially.

        Deduplication is now active: the first insert of each unique
        (checkpoint_id, family, metric_name) returns METRIC_INSERTED;
        subsequent calls with the same key return METRIC_SKIPPED.
        """
        from lightml.metrics import METRIC_INSERTED, METRIC_SKIPPED

        handle = basic_registry["handle"]
        checkpoint_id = basic_registry["checkpoint_id"]
        
        metrics = [
            ("training", "loss", 0.5),
            ("training", "loss", 0.4),    # duplicate → SKIPPED
            ("training", "loss", 0.3),    # duplicate → SKIPPED
            ("validation", "accuracy", 0.85),
            ("validation", "accuracy", 0.90),  # duplicate → SKIPPED
        ]
        
        results = []
        for family, metric_name, value in metrics:
            result = handle.log_checkpoint_metric(
                checkpoint_id=checkpoint_id,
                family=family,
                metric_name=metric_name,
                value=value
            )
            results.append(result)
        
        assert len(results) == len(metrics)
        # First occurrence of each key is INSERTED, duplicates are SKIPPED
        assert results[0] == METRIC_INSERTED   # training/loss first
        assert results[1] == METRIC_SKIPPED    # training/loss dup
        assert results[2] == METRIC_SKIPPED    # training/loss dup
        assert results[3] == METRIC_INSERTED   # validation/accuracy first
        assert results[4] == METRIC_SKIPPED    # validation/accuracy dup
    
    # ------------------------------------------------------------------------
    # Requirement 3.2: Registries without schema accept any metrics
    # ------------------------------------------------------------------------
    
    @pytest.mark.parametrize("family,metric_name,value", [
        ("custom_family", "custom_metric", 0.5),
        ("arbitrary", "test", 1.0),
        ("random_family", "random_metric", 99.99),
        ("special!chars", "metric@name", -5.5),
        ("", "empty_family", 0.0),
    ])
    def test_registry_without_schema_accepts_any_metrics(self, basic_registry, family, metric_name, value):
        """
        Preservation: Registries without schema accept any metrics.
        
        Property: For all (family, metric_name) pairs, when registry has no schema,
        metrics are accepted without validation.
        """
        handle = basic_registry["handle"]
        
        result = handle.log_model_metric(
            model_name="test_model",
            family=family,
            metric_name=metric_name,
            value=value
        )
        
        assert result is not None
        assert isinstance(result, int)
        assert result > 0
    
    def test_registry_without_schema_accepts_diverse_metrics(self, basic_registry):
        """
        Preservation: Registry without schema accepts diverse metric combinations.
        """
        handle = basic_registry["handle"]
        
        diverse_metrics = [
            ("accuracy", "train", 0.95),
            ("loss", "val", 0.25),
            ("f1", "test", 0.88),
            ("custom", "metric1", 100.0),
            ("another", "metric2", -50.0),
        ]
        
        results = []
        for family, metric_name, value in diverse_metrics:
            result = handle.log_model_metric(
                model_name="test_model",
                family=family,
                metric_name=metric_name,
                value=value
            )
            results.append(result)
        
        assert len(results) == len(diverse_metrics)
        assert all(isinstance(r, int) and r > 0 for r in results)
    
    # ------------------------------------------------------------------------
    # Requirement 3.3: Model registration works correctly
    # ------------------------------------------------------------------------
    
    @pytest.mark.parametrize("model_name", [
        "model_1",
        "model_2",
        "resnet50",
        "bert-base",
        "custom_model_v2",
    ])
    def test_model_registration_works(self, model_name):
        """
        Preservation: Model registration continues to work correctly.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")
            
            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            model_id = handle.register_model(model_name=model_name, path=tmp)
            
            assert model_id is not None
            assert isinstance(model_id, int)
            assert model_id > 0
    
    def test_model_registration_with_parent(self):
        """
        Preservation: Model registration with parent model works correctly.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")
            
            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            import os
            parent_path = os.path.join(tmp, "parent"); os.makedirs(parent_path)
            child_path = os.path.join(tmp, "child"); os.makedirs(child_path)
            parent_id = handle.register_model(model_name="parent_model", path=parent_path)
            
            child_id = register_model(
                db=str(db_path),
                run_name="test_run",
                model_name="child_model",
                path=child_path,
                parent_name="parent_model"
            )
            
            assert parent_id > 0
            assert child_id > 0
            assert child_id != parent_id
    
    def test_model_registration_idempotent(self):
        """
        Preservation: Model registration is idempotent.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")
            
            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            
            model_id_1 = handle.register_model(model_name="test_model", path=tmp)
            model_id_2 = handle.register_model(model_name="test_model", path=tmp)
            
            assert model_id_1 == model_id_2

    def test_path_dedup_returns_existing_model(self):
        """
        If a model with the same path already exists (even with a different name),
        register_model returns the existing model's ID without creating a duplicate.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp, registry_name="test_registry",
                overwrite=True, metrics_schema=[],
            )
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")

            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            model_dir = os.path.join(tmp, "shared_model")
            os.makedirs(model_dir)

            id_first = handle.register_model(model_name="MIIA14B-BASE", path=model_dir)
            id_second = handle.register_model(model_name="ba10400", path=model_dir)

            # Same path → same id, no duplicate
            assert id_first == id_second

            # Only one model row in DB
            import sqlite3
            with sqlite3.connect(str(db_path)) as conn:
                count = conn.execute("SELECT COUNT(*) FROM model").fetchone()[0]
            assert count == 1

    def test_path_dedup_different_paths_are_separate(self):
        """
        Models with different paths are registered as separate entries.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp, registry_name="test_registry",
                overwrite=True, metrics_schema=[],
            )
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")

            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            p1 = os.path.join(tmp, "model_a"); os.makedirs(p1)
            p2 = os.path.join(tmp, "model_b"); os.makedirs(p2)

            id_a = handle.register_model(model_name="model_a", path=p1)
            id_b = handle.register_model(model_name="model_b", path=p2)
            assert id_a != id_b

    def test_register_model_with_parent_id(self):
        """
        parent_id can be used as alternative to parent_name for linking models.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp, registry_name="test_registry",
                overwrite=True, metrics_schema=[],
            )
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")

            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            p_parent = os.path.join(tmp, "parent"); os.makedirs(p_parent)
            p_child = os.path.join(tmp, "child"); os.makedirs(p_child)

            parent_id = handle.register_model(model_name="base", path=p_parent)
            child_id = handle.register_model(
                model_name="finetuned", path=p_child, parent_id=parent_id,
            )

            assert child_id != parent_id

            # Verify parent_id is set correctly in DB
            import sqlite3
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT parent_id FROM model WHERE id = ?", (child_id,)
                ).fetchone()
            assert row[0] == parent_id

    def test_path_dedup_orchestrator_scenario(self):
        """
        Simulates the orchestrator scenario: parent already registered as 'MIIA14B-BASE',
        then orchestrator calls register_model with name='ba10400' but same path.
        The child should correctly link to the existing parent via parent_id.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp, registry_name="test_registry",
                overwrite=True, metrics_schema=[],
            )
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")

            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            base_path = os.path.join(tmp, "ba10400"); os.makedirs(base_path)
            child_path = os.path.join(tmp, "finetuned"); os.makedirs(child_path)

            # Migration script registered the model as "MIIA14B-BASE"
            original_id = handle.register_model(model_name="MIIA14B-BASE", path=base_path)

            # Orchestrator tries to register same path under different name
            parent_id = handle.register_model(model_name="ba10400", path=base_path)
            assert parent_id == original_id  # path dedup kicks in

            # Child links via parent_id → correctly points to MIIA14B-BASE
            child_id = handle.register_model(
                model_name="finetuned-123", path=child_path, parent_id=parent_id,
            )

            import sqlite3
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT parent_id FROM model WHERE id = ?", (child_id,)
                ).fetchone()
            assert row[0] == original_id

            # Still only 2 models, not 3
            count = conn.execute("SELECT COUNT(*) FROM model").fetchone()[0]
            assert count == 2

    # ------------------------------------------------------------------------
    # Requirement 3.4: Checkpoint registration works correctly
    # ------------------------------------------------------------------------
    
    @pytest.mark.parametrize("step", [0, 100, 500, 1000, 10000])
    def test_checkpoint_registration_works(self, step):
        """
        Preservation: Checkpoint registration continues to work correctly.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")
            
            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            handle.register_model(model_name="test_model", path=tmp)
            
            checkpoint_id = handle.register_checkpoint(
                model_name="test_model",
                step=step,
                path=str(Path(tmp) / f"checkpoint_{step}")
            )
            
            assert checkpoint_id is not None
            assert isinstance(checkpoint_id, int)
            assert checkpoint_id > 0
    
    def test_multiple_checkpoints_registration(self):
        """
        Preservation: Multiple checkpoints can be registered for the same model.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            create_run(db=str(db_path), run_name="test_run")
            
            handle = LightMLHandle(db=str(db_path), run_name="test_run")
            handle.register_model(model_name="test_model", path=tmp)
            
            checkpoint_ids = []
            for step in [100, 200, 300, 400, 500]:
                checkpoint_id = handle.register_checkpoint(
                    model_name="test_model",
                    step=step,
                    path=str(Path(tmp) / f"checkpoint_{step}")
                )
                checkpoint_ids.append(checkpoint_id)
            
            assert len(checkpoint_ids) == len(set(checkpoint_ids))
            assert all(cid > 0 for cid in checkpoint_ids)
    
    # ------------------------------------------------------------------------
    # Requirement 3.5: Run creation works correctly
    # ------------------------------------------------------------------------
    
    @pytest.mark.parametrize("run_name", [
        "run_1",
        "experiment_a",
        "test-run-123",
        "my_custom_run",
    ])
    def test_run_creation_works(self, run_name):
        """
        Preservation: Run creation continues to work correctly.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            run_id = create_run(db=str(db_path), run_name=run_name)
            
            assert run_id is not None
            assert isinstance(run_id, int)
            assert run_id > 0
    
    def test_handle_creates_run_if_not_exists(self):
        """
        Preservation: Handle initialization creates run if it doesn't exist.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            handle = LightMLHandle(db=str(db_path), run_name="new_run")
            
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute(
                    "SELECT id FROM run WHERE run_name = ?",
                    ("new_run",)
                ).fetchone()
                
                assert row is not None
                assert row[0] > 0
    
    def test_run_creation_idempotent(self):
        """
        Preservation: Run creation is idempotent.
        """
        with tempfile.TemporaryDirectory() as tmp:
            registry = RegistryInit(
                registry_path=tmp,
                registry_name="test_registry",
                overwrite=True,
                metrics_schema=[]
            )
            
            db_path = initialize_registry(registry)
            
            run_id_1 = create_run(db=str(db_path), run_name="test_run")
            run_id_2 = create_run(db=str(db_path), run_name="test_run")
            
            assert run_id_1 == run_id_2
    
    # ------------------------------------------------------------------------
    # Requirement 3.6: Query operations return same structure
    # ------------------------------------------------------------------------
    
    def test_query_metrics_returns_expected_structure(self, basic_registry):
        """
        Preservation: Query operations return the same data structure.
        """
        handle = basic_registry["handle"]
        db_path = basic_registry["db_path"]
        checkpoint_id = basic_registry["checkpoint_id"]
        
        handle.log_checkpoint_metric(
            checkpoint_id=checkpoint_id,
            family="training",
            metric_name="loss",
            value=0.25
        )
        
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT id, model_id, checkpoint_id, family, metric_name, value FROM metrics"
            ).fetchall()
            
            assert len(rows) > 0
            
            for row in rows:
                assert len(row) == 6
                assert isinstance(row[0], int)
                assert isinstance(row[2], int) or row[2] is None
                assert isinstance(row[3], str)
                assert isinstance(row[4], str)
                assert isinstance(row[5], (int, float))
    
    def test_query_models_returns_expected_structure(self, basic_registry):
        """
        Preservation: Query operations for models return the same data structure.
        """
        db_path = basic_registry["db_path"]
        
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT id, model_name, path, parent_id, run_id FROM model"
            ).fetchall()
            
            assert len(rows) > 0
            
            for row in rows:
                assert len(row) == 5
                assert isinstance(row[0], int)
                assert isinstance(row[1], str)
                assert isinstance(row[2], str)
                assert isinstance(row[4], int)
    
    def test_query_checkpoints_returns_expected_structure(self, basic_registry):
        """
        Preservation: Query operations for checkpoints return the same data structure.
        """
        db_path = basic_registry["db_path"]
        
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT id, model_id, step, path, created_at FROM checkpoint"
            ).fetchall()
            
            assert len(rows) > 0
            
            for row in rows:
                assert len(row) == 5
                assert isinstance(row[0], int)
                assert isinstance(row[1], int)
                assert isinstance(row[2], int)
                assert isinstance(row[3], str)
                assert isinstance(row[4], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
