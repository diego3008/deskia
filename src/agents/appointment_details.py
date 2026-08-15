
from datetime import datetime

from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel


class AppointmentDetails(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    cancellation_reason: str | None = None


DETAILS_PROMPT = """Extract only appointment details from the user message.
Business timezone: {business_timezone}. Current time: {current_time}.
Return starts_at and ends_at only when both are explicitly known or can be resolved
unambiguously in the business timezone. Do not invent a duration. Return null for
unknown or ambiguous values. Extract a cancellation reason only when stated.
You do not decide whether to book, cancel, reschedule, or call any tool.

User message: {message}"""


def extract_appointment_details(*, message: str, business_timezone: str, current_time: datetime) -> AppointmentDetails:
    model = ChatOpenRouter(model="google/gemini-3.5-flash-lite", temperature=0)
    structured = model.with_structured_output(AppointmentDetails)
    return structured.invoke(
        DETAILS_PROMPT.format(
            message=message,
            business_timezone=business_timezone,
            current_time=current_time.isoformat(),
        )
    )
