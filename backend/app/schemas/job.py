from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.models.job import JobStatus


class JobOut(BaseModel):
    id: int
    name: str
    status: JobStatus
    total: int
    processed: int
    errors: int
    skipped: int
    api_cost_usd: float
    speed_per_min: Optional[float]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobLogOut(BaseModel):
    id: int
    job_id: int
    photo_id: Optional[int]
    level: str
    message: str
    details: Optional[Dict[str, Any]]
    duration_ms: Optional[int]
    ai_provider: Optional[str]
    api_cost_usd: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}
