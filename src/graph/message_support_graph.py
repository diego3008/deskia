from langgraph.graph import END, START, StateGraph

from src.nodes import NODES
from src.state import MessageGraphState
from src.structured_outputs import MessageCategory
from src.graph.appointment_subgraph import appointment_adapter

APPOINTMENT_CATEGORIES = {
    MessageCategory.BOOK_APPOINTMENT,
    MessageCategory.CHECK_AVAILABILITY,
    MessageCategory.RESCHEDULE_APPOINTMENT,
    MessageCategory.CANCEL_APPOINTMENT,
    MessageCategory.VIEW_APPOINTMENT,
}

WRITER_CATEGORIES = {
    MessageCategory.GREETING,
    MessageCategory.SERVICE_INFORMATION,
    MessageCategory.SERVICE_DETAILS,
    MessageCategory.BUSINESS_INFORMATION,
}


class MessageSupportGraph:

    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_node("appointment_subgraph", appointment_adapter)

        workflow.add_node("message_writer", NODES["message_writer"])
        workflow.add_node("fallback_node", NODES["fallback"])

        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")

        workflow.add_conditional_edges(
            "category",
            self.route_by_category,
            {
                "appointment_management": "appointment_subgraph",
                "message_writer": "message_writer",
                "fallback_node": "fallback_node",
            },
        )
        workflow.add_edge("appointment_subgraph", END)
        workflow.add_edge("message_writer", END)
        workflow.add_edge("fallback_node", END)

        self.graph = workflow.compile()

    def route_by_category(self, state: MessageGraphState) -> str:
        raw_category = state.get("message_category")
        try:
            category = MessageCategory(raw_category)
        except (ValueError, TypeError):
            return "fallback_node"

        if category in APPOINTMENT_CATEGORIES or (
            category == MessageCategory.PROVIDE_INFORMATION
            and state.get("active_flow") == "booking"
        ):
            return "appointment_management"

        if category in WRITER_CATEGORIES:
            return "message_writer"

        return "fallback_node"


message_support_graph = MessageSupportGraph().graph
