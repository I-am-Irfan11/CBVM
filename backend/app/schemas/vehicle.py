from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.plates import normalize_plate, valid_plate

VehicleType = Literal["student", "staff", "bus", "visitor", "service", "emergency", "other"]


class VehicleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    number_plate: str = Field(min_length=6, max_length=20)
    vehicle_type: VehicleType
    owner_name: str = Field(min_length=1, max_length=100)
    student_id: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=100)
    vehicle_model: str | None = Field(default=None, max_length=80)
    status: Literal["active", "inactive"] = "active"

    @field_validator("number_plate")
    @classmethod
    def plate(cls, value):
        value = normalize_plate(value)
        if not valid_plate(value):
            raise ValueError("Enter a conventional Indian or Bharat-series registration")
        return value


class Movement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    camera_id: str = Field(default="main-gate-in", min_length=1, max_length=80)
    purpose: str = Field(default="Campus visit", min_length=1, max_length=240)
    custom_purpose: str | None = Field(default=None, max_length=240)
    tracking_id: str | None = Field(default=None, min_length=1, max_length=100)
    event_id: str | None = Field(default=None, min_length=1, max_length=100)
    detection_confidence: float = Field(default=1, ge=0, le=1)
    timestamp: datetime | None = None

    @field_validator("timestamp")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timestamp must include a UTC offset")
        return value


class MockRequest(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=80)
    direction: Literal["IN", "OUT"] = "IN"
