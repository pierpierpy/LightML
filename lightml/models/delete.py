from pydantic import BaseModel


class DeleteResult(BaseModel):
    """Summary of a model cascade deletion."""
    model_name: str
    model_id: int
    checkpoints_deleted: int
    metrics_deleted: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "model_name": "my-model",
                "model_id": 42,
                "checkpoints_deleted": 5,
                "metrics_deleted": 80,
            }
        }
    }

    def to_text(self) -> str:
        return (
            f"Deleted model '{self.model_name}' (id={self.model_id}): "
            f"{self.checkpoints_deleted} checkpoints, "
            f"{self.metrics_deleted} metrics removed."
        )
