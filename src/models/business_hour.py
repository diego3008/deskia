from datetime import time
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, ForeignKey, SmallInteger, Time, Uuid, text
from sqlmodel import Field, SQLModel


class BusinessHourBase(SQLModel):
    day_of_week: int = Field(sa_type=SmallInteger())
    start_time: time = Field(sa_type=Time(timezone=False))
    end_time: time = Field(sa_type=Time(timezone=False))
    business_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("businesses.id"),
            nullable=True,
            server_default=text("gen_random_uuid()"),
        ),
    )


class BusinessHour(BusinessHourBase, table=True):
    __tablename__ = "business_hours"
    __table_args__ = (
        CheckConstraint("start_time < end_time", name="business_hours_check"),
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="business_hours_day_of_week_check",
        ),
    )

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )
