from uuid import UUID

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Uuid, text
from sqlmodel import Field, SQLModel


class StaffServiceBase(SQLModel):
    business_staff_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("business_staff.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    service_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("services.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    custom_duration_minutes: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )


class StaffService(StaffServiceBase, table=True):
    __tablename__ = "staff_services"
