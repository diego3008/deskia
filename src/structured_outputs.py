
from enum import Enum

from pydantic import BaseModel, Field


class MessageCategory(str, Enum):
    service_request = "service_request"   
    confirmation = "confirmation"
    decline = "decline"                   
    customer_complaint = "customer_complaint"
    customer_feedback = "customer_feedback"
    greeting = "greeting"
    unrelated = "unrelated"
    service_inquiry = "service_inquiry"
    new_appointment = "new_appointment"
    reschedule_appointment = "reschedule_appointment"
    cancel_appointment = "cancel_appointment"
    check_availability = "check_availability"
    view_appointment = "view_appointment"


APPOINTMENT_INTENTS = {
    "new_appointment": "book_appointment",
    "check_availability": "check_availability",
    "reschedule_appointment": "reschedule_appointment",
    "cancel_appointment": "cancel_appointment",
    "view_appointment": "view_appointment",
}
APPOINTMENT_CATEGORIES = frozenset(APPOINTMENT_INTENTS) | {"service_request"}


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
