from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["employee", "manager", "hr", "admin"]
Classification = Literal["Public", "General_Internal", "Management", "HR_Confidential", "Restricted"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=3, max_length=500)


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: str
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class DocumentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    classification: Classification | None = None
    department: str | None = Field(default=None, max_length=80)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    department: str = Field(default="", max_length=80)
    role: Role
    password: str | None = Field(default=None, min_length=10, max_length=72, description="Omit to send an invite email")


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=80)
    role: Role | None = None
    is_active: bool | None = None


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class UploadFinalize(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    staging_path: str = Field(min_length=1, max_length=600)
    classification: Classification
    department: str = Field(default="", max_length=80)
