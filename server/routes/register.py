from fastapi import APIRouter
from lightml.registry import initialize_registry
from lightml.models.registry import RegistryInit
from fastapi import APIRouter
from lightml.registry import register_model
from lightml.models.registry import ModelCreate

router = APIRouter()

@router.post("/registry/init", tags=["registry"])
async def create_registry(registry: RegistryInit):
    db_path = initialize_registry(registry)
    return {"status": "ok", "db_path": str(db_path)}


@router.post("/models/register", tags=["models"])
async def register_model_route(model: ModelCreate):
    result = register_model(model.db, model.model_name, model.path, model.parent_name)
    if result == 1:
        return {"status": "ok", "model_name": model.model_name}
    else:
        return {"status": "error"}