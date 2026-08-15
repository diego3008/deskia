from datetime import datetime
from typing import Annotated, NotRequired, TypedDict
from uuid import UUID

from langgraph.graph import add_messages
from pydantic import BaseModel

from src.structured_outputs import (
    AppointmentOperation,
    AppointmentPhase,
    ConfirmationStatus,
    MessageCategory,
)


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


class AppointmentSelection(TypedDict, total=False):
    id: UUID
    service_id: UUID | None
    starts_at: datetime
    ends_at: datetime
    status: str
    active: bool


class AvailabilityEvidence(TypedDict, total=False):
    starts_at: datetime
    ends_at: datetime
    service_id: UUID | None
    available: bool
    checked_at: datetime
    verification_token: str | None


class PendingAppointmentAction(TypedDict, total=False):
    action_id: UUID
    operation: AppointmentOperation
    business_id: UUID
    customer_id: UUID
    appointment_id: UUID | None
    service_id: UUID | None
    requested_start: datetime | None
    requested_end: datetime | None
    selected_before: AppointmentSelection | None
    cancellation_reason: str | None


class AppointmentResult(TypedDict, total=False):
    appointment: AppointmentSelection
    message: str


class AppointmentError(TypedDict):
    code: str
    message: str
    retryable: bool


class AppointmentState(TypedDict, total=False):
    
    business_id: UUID
    business_timezone: str | None
    customer_id: UUID | None
    current_message: str
    messages: Annotated[list[str], add_messages]
    message_history_length: int

    operation: AppointmentOperation
    phase: AppointmentPhase
    service_id: UUID | None
    cancellation_reason: str | None
    requested_start: datetime | None
    requested_end: datetime | None
    selected_appointment: AppointmentSelection | None
    appointment_candidates: list[AppointmentSelection] | None
    availability_evidence: AvailabilityEvidence | None
    pending_action: PendingAppointmentAction | None
    confirmation_status: ConfirmationStatus
    confirmation_action_id: UUID | None
    result: AppointmentResult | None
    error: AppointmentError | None

class MessageGraphState(TypedDict):
    messages: Annotated[list, add_messages]
    current_message: str
    message_category: str
    message_response: str
    business_id: UUID
    business_timezone: str | None
    customer: dict | None
    active_flow: str | None
    customer_id: UUID | None
    active_appointment: dict | None
    confirmed_slot: dict | None
    service_plan: dict | None
    appointment: NotRequired[AppointmentState]
