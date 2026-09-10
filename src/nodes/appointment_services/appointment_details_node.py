from datetime import datetime

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_openrouter import ChatOpenRouter

from src.helpers import helpers
from src.models.appointment_details import AppointmentDetails
from src.state import MessageGraphState


APPOINTMENT_DETAILS_PROMPT = """Extract appointment details from the latest message and recent conversation.

Return only details the customer supplied. A start time requires both a date and a time. Resolve
relative dates using the current local date and timezone below. Never infer an appointment end time.

Current local datetime: {current_datetime}
Local timezone: {timezone}
Existing service: {existing_service_name}
Existing start: {existing_starts_at}

Recent conversation:
{history}

Latest message:
{message}
"""


def appointment_details_agent():
    prompt = PromptTemplate(
        template=APPOINTMENT_DETAILS_PROMPT,
        input_variables=[
            "message",
            "history",
            "existing_service_name",
            "existing_starts_at",
            "current_datetime",
            "timezone",
        ],
    )
    llm = ChatOpenRouter(model="google/gemini-3.7-flash", temperature=0)
    return prompt | llm.with_structured_output(AppointmentDetails)


def appointment_details_node(state: MessageGraphState) -> dict:
    current = state.get("current_message", "")
    message = current.content if hasattr(current, "content") else str(current)
    now = datetime.now().astimezone()
    extracted = appointment_details_agent().invoke(
        {
            "message": message,
            "history": helpers["build_recent_history"](
                state.get("messages", []), state.get("conversation_summary")
            ),
            "existing_service_name": state.get("service_name") or "Not provided",
            "existing_starts_at": (
                state["starts_at"].isoformat()
                if state.get("starts_at")
                else "Not provided"
            ),
            "current_datetime": now.isoformat(),
            "timezone": str(now.tzinfo),
        }
    )
    service_name = (
        extracted.service_name
        if extracted.service_name is not None
        else state.get("service_name")
    )
    starts_at = (
        extracted.starts_at
        if extracted.starts_at is not None
        else state.get("starts_at")
    )
    if isinstance(starts_at, datetime) and starts_at.utcoffset() is None:
        starts_at = starts_at.replace(tzinfo=now.tzinfo)
    result = {
        "service_name": service_name,
        "starts_at": starts_at,
        "pending_question": None,
        "next_action": "check_availability",
    }
    if service_name and starts_at:
        return result

    if not service_name and not starts_at:
        question = "¿Qué servicio deseas y para qué fecha y hora?"
    elif not service_name:
        question = "¿Qué servicio deseas reservar?"
    else:
        question = "¿Para qué fecha y hora deseas la cita?"
    return {
        **result,
        "messages": [AIMessage(content=question)],
        "pending_question": "appointment_details",
        "next_action": "collect_appointment_details",
    }
