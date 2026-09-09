

from typing_extensions import Literal

from langgraph.graph import END, START, StateGraph

from src.nodes import NODES
from src.state import MessageGraphState
from src.graph.user_services_validation_subgraph import user_services_subgraph
from src.graph.appointment_services_subgraph import appointment_services_subgraph
from src.helpers.workflow import customer_validation_pending, has_validated_customer
from src.structured_outputs import APPOINTMENT_CATEGORIES

WRITER_CATEGORIES = {
    "greeting",
    "customer_complaint",
    "customer_feedback",
    "decline",
}


class AppointmentBooking:

    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        workflow.add_node("message_listener", NODES["message_listener"])
        workflow.add_node("should_compact", NODES["compact_context"])
        workflow.add_node("category", NODES["message_categorizer"])
        workflow.add_node("user_services", user_services_subgraph)
        workflow.add_node("appointment_services", appointment_services_subgraph)
        workflow.add_node("message_writer", NODES["message_writer"])
        workflow.add_node("fallback", fallback_node)

        workflow.add_edge(START, "message_listener")
        workflow.add_edge("message_listener", "should_compact")
        workflow.add_edge("should_compact", "category")

        workflow.add_conditional_edges(
            "category",
            route_by_category,
            {
                "user_services": "user_services",
                "appointment_services": "appointment_services",
                "message_writer": "message_writer",
                "fallback": "fallback",
            },
        )

        workflow.add_conditional_edges(
            "user_services",
            route_after_user_services,
            {
                "appointment_services": "appointment_services",
                "message_writer": "message_writer",
            },
        )
        workflow.add_edge("appointment_services", "message_writer")
        workflow.add_edge("message_writer", END)
        workflow.add_edge("fallback", END)

        self.graph = workflow.compile()

def route_by_category(
    state: MessageGraphState,
) -> Literal["user_services", "appointment_services", "message_writer", "fallback"]:
    if customer_validation_pending(state):
        return "user_services"

    category = state.get("message_category")
    if category in WRITER_CATEGORIES:
        return "message_writer"

    in_appointment_flow = state.get("current_flow") == "appointment_services"
    if category in APPOINTMENT_CATEGORIES or in_appointment_flow:
        if has_validated_customer(state):
            return "appointment_services"
        return "user_services"

    if category == "service_inquiry":
        return "user_services"

    return "fallback"


def route_after_user_services(
    state: MessageGraphState,
) -> Literal["appointment_services", "message_writer"]:
    if (
        state.get("current_flow") == "appointment_services"
        and has_validated_customer(state)
        and not customer_validation_pending(state)
    ):
        return "appointment_services"
    return "message_writer"


def fallback_node(state: MessageGraphState) -> dict:
    return {
        "messages": [
                    {
                        "role": "assistant",
                        "content": (
                            "Puedo ayudarte con citas, cambios o cancelaciones."
                            "¿Qué necesitas?."
                        ),
                    }
                ],
        "current_flow": None,
        "next_action": "clarify_intent",
    }




booking_graph = AppointmentBooking().graph
