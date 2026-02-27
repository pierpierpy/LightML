from pydantic import BaseModel

class CheckpointCreate(BaseModel):
    db: str
    model_name: str
    step: int
    path: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "db": "my_registry/main.db",
                "model_name": "resnet50",
                "step": 1000,
                "path": "/home/pier/checkpoints/ckpt_1000.pt"
            }
        }
    }