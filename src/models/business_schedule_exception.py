from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlmodel import Field, SQLModel


class BusinessScheduleExceptionBase(SQLModel):
    business_id: UUID = Field(
        sa_column=Column(
            "business_id",
            ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    exception_date: date = Field(sa_type=Date())
    is_closed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    start_time: time | None = Field(
        default=None,
        sa_column=Column(Time(timezone=False), nullable=True),
    )
    end_time: time | None = Field(
        default=None,
        sa_column=Column(Time(timezone=False), nullable=True),
    )
    reason: str | None = Field(default=None, max_length=255)


class BusinessScheduleException(BusinessScheduleExceptionBase, table=True):
    __tablename__ = "business_schedule_exceptions"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "exception_date",
            name="business_schedule_exception_unique_date",
        ),
        CheckConstraint(
            "((is_closed = true AND start_time IS NULL AND end_time IS NULL) "
            "OR (is_closed = false AND start_time IS NOT NULL "
            "AND end_time IS NOT NULL AND start_time < end_time))",
            name="business_schedule_exception_time_check",
        ),
        Index(
            "idx_business_schedule_exceptions_lookup",
            "business_id",
            "exception_date",
        ),
    )

    id: UUID | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
