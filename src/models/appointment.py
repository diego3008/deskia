from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Text, Uuid, func, text
from sqlmodel import Field, SQLModel


class AppointmentBase(SQLModel):
    starts_at: datetime = Field(sa_type=DateTime(timezone=True))
    ends_at: datetime = Field(sa_type=DateTime(timezone=True))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    business_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("businesses.id"),
            nullable=False,
            server_default=text("gen_random_uuid()"),
        )
    )
    customer_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("customers.id"),
            nullable=False,
            server_default=text("gen_random_uuid()"),
        )
    )
    active: bool | None = Field(
        default=True,
        sa_column=Column(Boolean, nullable=True, server_default=text("true")),
    )
    status: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey(
                "appointment_status_codes.id",
                onupdate="RESTRICT",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
    )
    cancellation_reason: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    cancelled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    business_staff_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("business_staff.id"),
            nullable=True,
            server_default=text("gen_random_uuid()"),
        ),
    )
    service_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("services.id", onupdate="CASCADE"),
            nullable=True,
            server_default=text("gen_random_uuid()"),
        ),
    )



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
        description="The UUID of the customer who requested the appointment."
    )