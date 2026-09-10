from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, func, text
from sqlmodel import Field, SQLModel


class BusinessStaffBase(SQLModel):
    business_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            "business_id",
            ForeignKey("businesses.id", onupdate="RESTRICT"),
            nullable=True,
            server_default=text("gen_random_uuid()"),
        ),
    )
    first_name: str | None = Field(
        default="",
        sa_column=Column(Text, nullable=True, server_default=text("''")),
    )
    last_name: str | None = Field(
        default="",
        sa_column=Column(Text, nullable=True, server_default=text("''")),
    )
    active: bool | None = Field(
        default=True,
        sa_column=Column(Boolean, nullable=True, server_default=text("true")),
    )
    email: str | None = Field(
        default="",
        sa_column=Column(Text, nullable=True, server_default=text("''")),
    )
    phone: str | None = Field(
        default="",
        sa_column=Column(Text, nullable=True, server_default=text("''")),
    )


class BusinessStaff(BusinessStaffBase, table=True):
    __tablename__ = "business_staff"

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
