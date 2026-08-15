"""Pure response helpers for appointment read flows."""

from langchain_core.messages import AIMessage

from src.state import AppointmentState


def availability_response_node(state: AppointmentState) -> dict:
    error = state.get("error")
    if error:
        return {"messages": [AIMessage(content=error["message"])]}

    evidence = state.get("availability_evidence") or {}
    if evidence.get("available") is True:
        return {"messages": [AIMessage(content="That appointment time is available.")]}
    if evidence.get("available") is False:
        return {"messages": [AIMessage(content="That appointment time is not available.")]}
    return {"messages": [AIMessage(content="Please provide an appointment time to check.")]}


def lookup_response_node(state: AppointmentState) -> dict:
    error = state.get("error")
    if error:
        return {"messages": [AIMessage(content=error["message"])]}

    candidates = state.get("appointment_candidates")
    if candidates == []:
        return {"messages": [AIMessage(content="I could not find an upcoming appointment.")]}
    if candidates:
        return {
            "messages": [
                AIMessage(
                    content="I found multiple appointments. Which appointment would you like to manage?"
                )
            ]
        }

    selected = state.get("selected_appointment")
    if selected:
        return {"messages": [AIMessage(content="I found your appointment.")]}
    return {"messages": [AIMessage(content="Please identify the appointment you would like to view.")]}
