"""
Shared fixtures for LightML test suites.

These re-create a fresh temporary registry per test — identical to the
pattern used in test_bugfix.py but factored into a reusable conftest.
"""

import tempfile
import pytest
from pathlib import Path

from lightml.registry import initialize_registry, create_run
from lightml.models.registry import RegistryInit
from lightml.handle import LightMLHandle


@pytest.fixture
def fresh_registry():
    """Yield a minimal registry with one run and one model, no schema.

    Keys in the returned dict:
        db_path, tmp_dir, handle
    """
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="test_registry",
            overwrite=True,
            metrics_schema=[],
        )
        db_path = str(initialize_registry(registry))
        create_run(db=db_path, run_name="test_run")

        handle = LightMLHandle(db=db_path, run_name="test_run")
        handle.register_model(model_name="model_a", path=tmp)

        yield {
            "db_path": db_path,
            "tmp_dir": tmp,
            "handle": handle,
        }


@pytest.fixture
def two_model_registry():
    """Registry with two models pre-loaded with metrics for comparison tests.

    Models: model_a (baseline), model_b (candidate).
    Both have 'bench' family with metrics acc and f1.
    model_a: acc=0.80, f1=0.75
    model_b: acc=0.85, f1=0.70
    """
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="cmp_registry",
            overwrite=True,
            metrics_schema=[],
        )
        db_path = str(initialize_registry(registry))
        create_run(db=db_path, run_name="run1")

        h = LightMLHandle(db=db_path, run_name="run1")
        path_a = Path(tmp) / "model_a"; path_a.mkdir()
        path_b = Path(tmp) / "model_b"; path_b.mkdir()
        h.register_model(model_name="model_a", path=str(path_a))
        h.register_model(model_name="model_b", path=str(path_b))

        h.log_model_metric("model_a", "bench", "acc", 0.80)
        h.log_model_metric("model_a", "bench", "f1", 0.75)

        h.log_model_metric("model_b", "bench", "acc", 0.85)
        h.log_model_metric("model_b", "bench", "f1", 0.70)

        yield {
            "db_path": db_path,
            "tmp_dir": tmp,
            "handle": h,
        }
