"""Mongo document contracts for auxiliary collections."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Visitor(BaseModel):
    vehicle_id: str
    visitor_name: str
    organization: str | None = None
    phone: str | None = None
    host_department: str
    person_to_visit: str
    expected_exit_time: datetime | None = None


class Bus(BaseModel):
    vehicle_id: str
    bus_number: str
    route: str
    driver_name: str
    driver_phone: str | None = None
    capacity: int = Field(gt=0)
    status: Literal["active", "inactive"] = "active"


class Camera(BaseModel):
    camera_name: str
    location: str
    direction: Literal["IN", "OUT"]
    health_status: Literal["idle", "online", "offline", "mock"] = "idle"
    last_frame_time: datetime | None = None
