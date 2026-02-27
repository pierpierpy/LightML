from fastapi import APIRouter
import lightml.models.checkpoints as chkp
from lightml.checkpoints import register_checkpoint
router = APIRouter()

@router.post("/checkpoints/register", tags=["checkpoints"])
async def register_checkpoint_route(data: chkp.CheckpointCreate):
    result = register_checkpoint(
        db=data.db,
        model_name=data.model_name,
        step=data.step,
        path=data.path,
    )

    if result == 1:
        return {"status": "ok"}
    else:
        return {"status": "error"}