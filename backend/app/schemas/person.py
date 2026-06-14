from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class PersonCreate(BaseModel):
    name: str
    alias: Optional[str] = None
    birthdate: Optional[date] = None
    notes: Optional[str] = None
    relationship_type: Optional[str] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    alias: Optional[str] = None
    birthdate: Optional[date] = None
    notes: Optional[str] = None
    relationship_type: Optional[str] = None
    profile_face_id: Optional[int] = None


class PersonOut(BaseModel):
    id: int
    name: str
    alias: Optional[str]
    birthdate: Optional[date]
    relationship_type: Optional[str]
    profile_face_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class PersonDetail(PersonOut):
    notes: Optional[str]
    face_count: int
