from pydantic import Field
from uuid import UUID

from anthropic import BaseModel


class CustomerCreate(BaseModel):
    business_id: UUID = Field(
        description="The UUID of the business that received the message."
    )
    email: str = Field(description="The customer's email address (unique lookup key).")
    first_name: str = Field(description="The customer's first name.")
    last_name: str = Field(description="The customer's last name.")


class CustomerInput(BaseModel):
    email: str = Field(description="The customer's email address (unique lookup key).")
    first_name: str = Field(description="The customer's first name.")
    last_name: str = Field(description="The customer's last name.")
