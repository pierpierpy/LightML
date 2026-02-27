from fastapi import APIRouter
import lightml.models.metrics as mt 
from lightml.metrics import add_metric

router = APIRouter()

@router.post("/metrics/add", tags=["metrics"])
async def add_metric_route(metric: mt.MetricCreate):
    result = add_metric(
        db_path=metric.db,
        model_name=metric.model_name,
        family=metric.family,
        metric_name=metric.metric_name,
        value=metric.value,
    )

    if result == 1:
        return {"status": "ok"}
    else:
        return {"status": "error"}