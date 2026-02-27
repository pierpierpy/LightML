import tempfile
from lightml.registry import initialize_registry, register_model
from lightml.models.registry import RegistryInit, ModelCreate

def test_initialize_and_register():
    with tempfile.TemporaryDirectory() as tmp:
        registry = RegistryInit(
            registry_path=tmp,
            registry_name="test_registry",
            overwrite=True,
        )

        db_path = initialize_registry(registry)

        model = ModelCreate(
            model_name="m1",
            path=tmp,
            db=str(db_path),
        )

        assert register_model(model) == 1