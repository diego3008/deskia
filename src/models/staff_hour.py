from datetime import time
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, ForeignKey, SmallInteger, Time, Uuid, text
from sqlmodel import Field, SQLModel


class StaffHourBase(SQLModel):
    staff_id: UUID = Field(
        sa_column=Column(
            "staff_id",
            Uuid(as_uuid=True),
            ForeignKey("business_staff.id"),
            nullable=False,
        )
    )
    day_of_week: int = Field(sa_type=SmallInteger())
    start_time: time = Field(sa_type=Time(timezone=False))
    end_time: time = Field(sa_type=Time(timezone=False))


class StaffHour(StaffHourBase, table=True):
    __tablename__ = "staff_hours"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6"),
        CheckConstraint("start_time < end_time"),
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
