

from src.state import MessageGraphState


def message_listener_node(state: MessageGraphState) -> MessageGraphState:
    last_message = state["messages"][-1]
    body = last_message.content if hasattr(last_message, "content") else str(last_message)

    if not str(body).strip():
        return {"message_response": ""}

    return {
        "current_message": last_message,
        "message_response": "",
    }
