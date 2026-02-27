from pydantic import BaseModel, Field
from pathlib import Path
from typing import List, Dict


class ModelBase(BaseModel):
    model_name: str = Field(..., min_length=1)
    path: Path
    db: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "model_name": "resnet50",
                "path": "/home/pier/models/resnet50",
                "db": "my_registry/main.db"
            }
        }
    }


class ModelCreate(ModelBase):
    pass


class ModelRead(ModelBase):
    model_id: int

    model_config = {
        "from_attributes": True
    }


class RegistryBase(BaseModel):
    registry_path: str
    registry_name: str
    metrics_schema: List[Dict]
    overwrite: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "registry_path": "my_registry",
                "registry_name": "main",
                "metrics_schema": [
                    {
                        "family": "benchmarks_ita",
                        "metrics": {
                            "Hella": "float",
                            "MMLU": "float"
                        }
                    }
                ],
                "overwrite": True
            }
        }
    }


class RegistryInit(RegistryBase):
    pass