from pydantic import BaseModel

class MetricCreate(BaseModel):
    db: str
    model_name: str
    family: str
    metric_name: str
    value: float
    run_name: str | None = None
    checkpoint_id: int | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "db": "my_registry/main.db",
                "model_name": "resnet50",
                "family": "benchmarks_ita",
                "metric_name": "Hella",
                "value": 0.82,
                "run_name": "experiment_001"
            }
        }
    }