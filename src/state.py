from typing import Annotated, List, Optional, TypedDict
from typing_extensions import Literal
from uuid import UUID

from langgraph.graph import add_messages
from pydantic import BaseModel


class State(TypedDict):
    messages: Annotated[list, add_messages]  # reducer: appends, never overwrites
    step_log: Annotated[list[str], list.__add__]  # accumulates node names visited


class OutBoundsMessge(TypedDict):
    response: str

class AppointmentBookingState(TypedDict):
    messages: Annotated[list, add_messages]
    message_category: str
    current_flow: str
    next_action: str


class UserValidationState(TypedDict):
    business_id: UUID | None
    messages: Annotated[list, add_messages]
    message_category: str
    current_flow: str | None
    pending_question: str | None
    customer_status: str | None
    next_action: str
    user_data: dict
    customer: dict | None
    customer_id: UUID | str | None
    retrieved_services: str | None

class ServicesInquiryNode(TypedDict):
    messages: Annotated[list, add_messages]
    message_category: str
    current_flow: str
    next_action: str
    user_data: dict = {}
    retrieved_services: str | None

class MessageGraphState(TypedDict):
    messages: Annotated[list, add_messages]
    current_message: str
    message_category: str
    message_response: str
    business_id: UUID
    customer: dict | None
    current_flow: str | None
    next_action: str
    customer_id: UUID | str | None
    active_appointment: dict | None
    confirmed_slot: dict | None
    pending_question: str | None
    customer_status: str | None
    user_data: dict = {}
    retrieved_services: str | None
