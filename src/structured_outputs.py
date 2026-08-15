
from enum import Enum

from pydantic import BaseModel, Field


class AppointmentOperation(str, Enum):
    BOOK = "book"
    CHECK_AVAILABILITY = "check_availability"
    VIEW = "view"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"


class AppointmentPhase(str, Enum):
    COLLECTING = "collecting"
    LOOKING_UP = "looking_up"
    CHECKING_AVAILABILITY = "checking_availability"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConfirmationStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MessageCategory(str, Enum):
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    RESCHEDULE_APPOINTMENT = "RESCHEDULE_APPOINTMENT"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    VIEW_APPOINTMENT = "VIEW_APPOINTMENT"
    SERVICE_INFORMATION = "SERVICE_INFORMATION"
    SERVICE_DETAILS = "SERVICE_DETAILS"
    BUSINESS_INFORMATION = "BUSINESS_INFORMATION"
    PROVIDE_INFORMATION = "PROVIDE_INFORMATION"
    GREETING = "GREETING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNCLEAR = "UNCLEAR"


class CategorizerMessageOutput(BaseModel):
    category: MessageCategory = Field(..., description="The category assigned to the message, indicating its type based on predefined rules.")


class BookingIntent(str, Enum):
    book = "book"
    reschedule = "reschedule"
    unknown = "unknown"


class PlannerIntentOutput(BaseModel):
    intent: BookingIntent = Field(
        ...,
        description="Whether the customer wants to book a NEW appointment (book), "
        "change an EXISTING one (reschedule), or it is not yet clear (unknown).",
    )
