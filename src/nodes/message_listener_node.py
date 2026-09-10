

from src.state import MessageGraphState


def message_listener_node(state: MessageGraphState) -> MessageGraphState:
    last_message = state["messages"][-1]
    body = last_message.content if hasattr(last_message, "content") else str(last_message)

    if not str(body).strip():
        return {
            "message_response": "",
            "appointment_outcome": None,
            "email_draft": None,
            "email_confirmation": None,
        }

    return {
        "current_message": last_message,
        "message_response": "",
        "retrieved_services": "",
        "appointment_outcome": None,
        "email_draft": None,
        "email_confirmation": None,
    }
