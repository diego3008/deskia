from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AppointmentIntervalRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime


class AppointmentBookingRequest(AppointmentIntervalRequest):
    business_id: UUID
    customer_id: UUID


class AppointmentRescheduleRequest(AppointmentIntervalRequest):
    business_id: UUID
    customer_id: UUID


class AppointmentCancellationRequest(BaseModel):
    business_id: UUID
    customer_id: UUID
    reason: str | None = Field(default=None, max_length=500)


class AppointmentSummary(BaseModel):
    id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime
    active: bool


class AppointmentCancellationResponse(BaseModel):
    id: UUID
    status: str
    cancelled_at: datetime
    starts_at: datetime
    ends_at: datetime


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
