from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.photo import PhotoStatus


class PhotoBase(BaseModel):
    id: int
    path: str
    filename: str
    taken_at: Optional[datetime]
    width: Optional[int]
    height: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    status: PhotoStatus
    thumb_small: Optional[str]
    thumb_medium: Optional[str]
    is_video: bool = False
    duration_seconds: Optional[float] = None
    is_favorite: bool = False
    is_archived: bool = False
    is_trashed: bool = False
    user_rating: Optional[int] = None

    model_config = {"from_attributes": True}


class PhotoDetail(PhotoBase):
    description: Optional[str]
    camera_make: Optional[str]
    camera_model: Optional[str]
    lens_model: Optional[str]
    focal_length: Optional[float]
    aperture: Optional[float]
    shutter_speed: Optional[str]
    iso: Optional[int]
    altitude: Optional[float]
    city: Optional[str]
    country: Optional[str]
    location_name: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    processed_at: Optional[datetime]
    # editable metadata
    title: Optional[str] = None
    caption: Optional[str] = None
    keywords: Optional[str] = None
    user_description: Optional[str] = None
    artist: Optional[str] = None


class PhotoListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[PhotoBase]


class TimelineGroup(BaseModel):
    date: str
    count: int
    photos: List[PhotoBase]
