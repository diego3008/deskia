from langchain_core.messages import AIMessage, HumanMessage

from src.agents.message_writer import message_writer
from src.state import MessageGraphState


def message_writer_node(state: MessageGraphState) -> MessageGraphState:
    current = state["current_message"]
    body = current.content if hasattr(current, "content") else str(current)
    category = state["message_category"]
    is_first_message = sum(1 for m in state["messages"] if isinstance(m, HumanMessage)) == 1

    result = message_writer().invoke({
        "message_content": body,
        "message_category": category,
        "is_first_message": is_first_message,
    })

    return {
        "message_response": result["response"],
        "messages": [AIMessage(content=result["response"])],
    }
