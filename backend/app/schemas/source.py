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
    scan_interval_minutes: int = 0
    detect_deletions: bool = True
    ai_provider: Optional[str] = None


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    watch_enabled: Optional[bool] = None
    recursive: Optional[bool] = None
    exclusion_patterns: Optional[str] = None
    scan_interval_minutes: Optional[int] = None
    detect_deletions: Optional[bool] = None
    ai_provider: Optional[str] = None


class SourceOut(BaseModel):
    id: int
    path: str
    name: Optional[str]
    enabled: bool
    watch_enabled: bool
    recursive: bool
    exclusion_patterns: Optional[str]
    locked: bool
    scan_interval_minutes: int
    detect_deletions: bool
    ai_provider: Optional[str]
    last_scan_at: Optional[datetime]
    last_scan_count: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanResult(BaseModel):
    task_id: str
    message: str
