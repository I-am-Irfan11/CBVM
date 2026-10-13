from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.plates import normalize_plate, valid_plate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PurposeInput(StrictModel):
    purpose_name: str = Field(min_length=1, max_length=120)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)


class VisitorInput(StrictModel):
    number_plate: str = Field(min_length=6, max_length=20)
    vehicle_type: Literal["visitor", "service", "emergency", "other"] = "visitor"
    visitor_name: str = Field(min_length=1, max_length=100)
    organization: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    host_department: str = Field(min_length=1, max_length=100)
    person_to_visit: str = Field(min_length=1, max_length=100)
    expected_exit_time: datetime | None = None
    purpose: str = Field(default="Guest Visit", min_length=1, max_length=120)
    custom_purpose: str | None = Field(default=None, max_length=240)
    camera_id: str = "main-gate-in"
    review_id: str | None = None

    @field_validator("number_plate")
    @classmethod
    def plate(cls, value):
        value = normalize_plate(value)
        if not valid_plate(value):
            raise ValueError("Enter a valid Indian registration")
        return value

    @field_validator("expected_exit_time")
    @classmethod
    def aware(cls, value):
        if value and value.utcoffset() is None:
            raise ValueError("Expected exit must include a UTC offset")
        return value


class BusInput(StrictModel):
    vehicle_id: str
    bus_number: str = Field(min_length=1, max_length=30)
    route_number: str = Field(min_length=1, max_length=120)
    driver_name: str = Field(min_length=1, max_length=100)
    driver_phone: str | None = Field(default=None, max_length=30)
    capacity: int = Field(default=48, ge=1, le=100)
    status: Literal["active", "inactive"] = "active"


class CameraInput(StrictModel):
    camera_name: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=120)
    direction: Literal["IN", "OUT", "BOTH"] = "IN"
    source: Literal["rtsp", "mp4", "webcam"] = "webcam"
    gate_line: list[float] = Field(default=[0.1, 0.5, 0.9, 0.5], min_length=4, max_length=4)
    inward_sign: Literal[-1, 1] = 1
    minimum_movement: float = Field(default=.03, gt=0, le=.5)
    active: bool = True

    @field_validator("gate_line")
    @classmethod
    def line(cls, value):
        if any(x < 0 or x > 1 for x in value) or value[:2] == value[2:]:
            raise ValueError("Gate line needs two distinct normalized points between 0 and 1")
        return value


class ReviewAction(StrictModel):
    action: Literal["confirm", "reject"]
    number_plate: str | None = Field(default=None, max_length=20)
    direction: Literal["IN", "OUT"] = "IN"
    purpose: str = Field(default="Campus visit", min_length=1, max_length=240)
    custom_purpose: str | None = Field(default=None, max_length=240)
    note: str = Field(default="", max_length=500)


class UserInput(StrictModel):
    # Test-only legacy field. Production account passwords are handled by Firebase.
    password: str | None = Field(default=None, min_length=12, max_length=256)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    full_name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "security", "department_staff"]
    department: str | None = Field(default=None, max_length=100)
    active: bool = True

    @field_validator("username", "email")
    @classmethod
    def lower(cls, value):
        return value.lower()

    @model_validator(mode="after")
    def department_required(self):
        if self.role == "department_staff" and not self.department:
            raise ValueError("Department staff require a department")
        return self


class RetentionInput(StrictModel):
    retention_days: int = Field(ge=1, le=3650)
