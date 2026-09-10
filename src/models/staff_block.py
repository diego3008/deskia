from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, model_validator
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, text
from sqlmodel import Field, SQLModel


class StaffBlockBase(SQLModel):
    business_staff_id: UUID = Field(
        sa_column=Column(
            "business_staff_id",
            ForeignKey("business_staff.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    start_at: datetime = Field(sa_type=DateTime(timezone=True))
    end_at: datetime = Field(sa_type=DateTime(timezone=True))
    block_type: str = Field(max_length=50)
    reason: str | None = Field(default=None, max_length=255)


class StaffBlock(StaffBlockBase, table=True):
    __tablename__ = "staff_blocks"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="staff_blocks_check"),
        Index("idx_staff_blocks_staff_dates", "business_staff_id", "start_at", "end_at"),
    )

    id: UUID | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )


class StaffBlockType(str, Enum):
    BREAK = "BREAK"
    MEETING = "MEETING"
    VACATION = "VACATION"
    PERSONAL = "PERSONAL"
    SICK_LEAVE = "SICK_LEAVE"
    MANUAL_BLOCK = "MANUAL_BLOCK"


class StaffBlockCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    block_type: StaffBlockType
    reason: str | None = Field(
        default=None,
        max_length=255,
    )

    @model_validator(mode="after")
    def validate_block(self):
        if self.start_at.tzinfo is None:
            raise ValueError("start_at must include a timezone")

        if self.end_at.tzinfo is None:
            raise ValueError("end_at must include a timezone")

        if self.start_at >= self.end_at:
            raise ValueError(
                "start_at must be before end_at"
            )

        return self
