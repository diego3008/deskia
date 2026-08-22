from typing import Annotated, List, Optional, TypedDict
from typing_extensions import Literal
from uuid import UUID

from langgraph.graph import add_messages
from pydantic import BaseModel


class State(TypedDict):
    messages: Annotated[list, add_messages]  # reducer: appends, never overwrites
    step_log: Annotated[list[str], list.__add__]  # accumulates node names visited


    

class IncomingMessage(BaseModel):
    """
    Normalized message sent to the agent service.
    Platform-agnostic — the agent never deals with raw Telegram objects.
    """
    platform: str
    chat_id: str
    user_id: str
    username: str | None = None
    metadata: dict = {}
    role: str = "user"
    content: str

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
    current_flow: str
    pending_question: str | None
    customer_status: str | None
    next_action: str
    user_data: dict

class ServicesInquiryNode(TypedDict):
    messages: Annotated[list, add_messages]
    message_category: str
    current_flow: str
    next_action: str
    user_data: dict = {}

class MessageGraphState(TypedDict):
    messages: Annotated[list, add_messages]
    current_message: str
    message_category: str
    message_response: str
    business_id: UUID
    customer: dict | None
    current_flow: str | None
    next_action: str
    customer_id: UUID | None
    active_appointment: dict | None
    confirmed_slot: dict | None
    pending_question: str | None
    customer_status: str | None
    user_data: dict = {}
