from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SourceCreate(BaseModel):
    path: str
    name: Optional[str] = None
    enabled: bool = True
    watch_enabled: bool = False
    recursive: bool = True
    exclusion_patterns: Optional[str] = "@eaDir,#recycle,@Thumb,.DS_Store"


class SourceOut(BaseModel):
    id: int
    path: str
    name: Optional[str]
    enabled: bool
    watch_enabled: bool
    recursive: bool
    exclusion_patterns: Optional[str]
    locked: bool
    last_scan_at: Optional[datetime]
    last_scan_count: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanResult(BaseModel):
    task_id: str
    message: str
