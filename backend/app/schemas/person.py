from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class PersonCreate(BaseModel):
    name: str
    alias: Optional[str] = None
    birthdate: Optional[date] = None
    notes: Optional[str] = None
    relationship_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    alias: Optional[str] = None
    birthdate: Optional[date] = None
    notes: Optional[str] = None
    relationship_type: Optional[str] = None
    profile_face_id: Optional[int] = None
    is_hidden: Optional[bool] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class PersonOut(BaseModel):
    id: int
    name: str
    alias: Optional[str]
    birthdate: Optional[date]
    relationship_type: Optional[str]
    profile_face_id: Optional[int]
    is_hidden: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class PersonDetail(PersonOut):
    notes: Optional[str]
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    face_count: int
    photo_count: int = 0
