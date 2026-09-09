from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class AppointmentCreate(BaseModel):
    business_id: UUID = Field(
        description="The UUID of the business that received the message."
    )
    starts_at: datetime = Field(
        description=(
            "The exact date and time requested by the user, including the hour "
            "(e.g. 2026-06-21T15:30:00). If the user only gave a date with no time, "
            "ask them to clarify the time before calling this tool."
        )
    )
    ends_at: datetime = Field(
        description=(
            "The approximate ending date and time of the appointment, including the hour. "
            "If the user didn't specify a duration, infer a reasonable default "
            "(e.g. 1 hour after starts_at) unless context suggests otherwise."
        )
    )
    customer_id: UUID = Field(
        description="The UUID of the customer for whom the appointment is being created."
    )

class AppointmentInput(BaseModel):
    starts_at: datetime = Field(
        description=(
            "The exact date and time requested by the user, including the hour "
            "(e.g. 2026-06-21T15:30:00). If the user only gave a date with no time, "
            "ask them to clarify the time before calling this tool."
        )
    )
    ends_at: datetime = Field(
        description=(
            "The approximate ending date and time of the appointment, including the hour. "
            "If the user didn't specify a duration, infer a reasonable default "
            "(e.g. 1 hour after starts_at) unless context suggests otherwise."
        )
    )


class AppointmentOutcome(BaseModel):
    status: Literal["succeeded"]
    operation: Literal["booked", "rescheduled", "cancelled"]
    operation_id: str = Field(min_length=1)
    appointment_id: str = Field(min_length=1)
    business_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    recipient_email: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    previous_starts_at: datetime | None = None

    @field_validator("operation_id", "appointment_id", "business_id", "customer_id")
    @classmethod
    def nonblank_id(cls, value):
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("starts_at", "ends_at", "previous_starts_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("timezone offset required")
        return value

    @model_validator(mode="after")
    def valid_slot(self):
        if self.operation != "cancelled" and self.starts_at is None:
            raise ValueError("confirmed start required")
        if self.ends_at is not None and (
            self.starts_at is None or self.ends_at <= self.starts_at
        ):
            raise ValueError("end must follow start")
        return self
