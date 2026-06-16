from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool
    totp_enabled: bool
    birthdate: Optional[str] = None
    avatar_path: Optional[str] = None
    last_login: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class UserDetail(UserOut):
    access_config: Optional[Dict[str, Any]] = None


class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: UserRole = UserRole.user
    access_config: Optional[Dict[str, Any]] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    access_config: Optional[Dict[str, Any]] = None


class PasswordSet(BaseModel):
    password: str


class ProfileUpdate(BaseModel):
    """Self-service profile edit (current user)."""
    name: Optional[str] = None
    email: Optional[str] = None
    birthdate: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
