"""
Shared Pydantic Schemas

Common data transfer objects (DTOs) used across multiple modules.
Feature-specific schemas should live in modules/<feature>/schemas.py
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    username: str
    role: str = "student"
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    profile_public: bool = True
    allow_contact: bool = True

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    
    # Stats
    reputation_score: int = 0
    total_simulations: int = 0
    published_simulations: int = 0
    
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SimulationBase(BaseModel):
    title: str
    description: str

class SimulationCreate(SimulationBase):
    pass

class SimulationResponse(SimulationBase):
    id: int
    author_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

