

from typing_extensions import Literal

from langgraph.graph import StateGraph, START, END

from src.nodes import NODES
from src.state import MessageGraphState
from src.graph.user_services_validation_subgraph import user_services_subgraph

class AppointmentBooking:

    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_node("user_services", user_services_subgraph)
        workflow.add_node("fallback", fallback_node)

        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "category")

        workflow.add_conditional_edges(
            "category",
            route_by_category,
            {
                "user_services": "user_services",
                "fallback": "fallback"
            }
        )

        workflow.add_edge("user_services", END)
        workflow.add_edge("fallback", END)

        self.graph = workflow.compile()

def route_by_category(state: MessageGraphState) -> Literal["user_services", "fallback"]:
    if state.get("message_category") in {
        "new_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "service_inquiry"
    }:
        return "user_services"
    return "fallback"


def fallback_node(state: MessageGraphState) -> dict:
    return {
        "current_flow": None,
        "next_action": "clarify_intent",
    }




booking_subgraph = AppointmentBooking().graph
