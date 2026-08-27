from langchain_core.messages import AIMessage, HumanMessage

from src.agents.message_writer import message_writer
from src.helpers import helpers
from src.state import MessageGraphState


def _workflow_context(state: MessageGraphState) -> str:
    fields = ("pending_question", "next_action", "customer_status")
    return "\n".join(
        f"{field}: {state[field]}"
        for field in fields
        if state.get(field) is not None
    ) or "No active workflow state."


def message_writer_node(state: MessageGraphState) -> MessageGraphState:
    messages = state.get("messages", [])
    latest = messages[-1] if messages else None
    if isinstance(latest, AIMessage) and not latest.tool_calls:
        content = (
            latest.content
            if isinstance(latest.content, str)
            else str(latest.content)
        )
        return {"message_response": content}

    current = state["current_message"]
    body = current.content if hasattr(current, "content") else str(current)
    category = state["message_category"]
    is_first_message = sum(1 for m in state["messages"] if isinstance(m, HumanMessage)) == 1
    retrieved_services = state.get("retrieved_services", "")

    result = message_writer().invoke(
        {
            "message_content": body,
            "message_category": category,
            "is_first_message": is_first_message,
            "conversation_history": helpers["build_recent_history"](state["messages"]),
            "workflow_context": _workflow_context(state),
            "retrieved_services": retrieved_services,
        }
    )

    return {
        "message_response": result["response"],
        "messages": [AIMessage(content=result["response"])],
    }
