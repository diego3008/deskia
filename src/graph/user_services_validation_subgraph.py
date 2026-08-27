
from langgraph.graph import END, START, StateGraph

from src.state import UserValidationState
from src.nodes.user_services_validation import NODES

class UserServicesValidation:

    def __init__(self):
        workflow = StateGraph(UserValidationState)
        workflow.add_node("user_validation", NODES["user_validation"])
        workflow.add_node("services_inquiry", NODES["services_inquiry"])
        workflow.add_node("customer_lookup", NODES["customer_lookup"])
        workflow.add_node("customer_creation", NODES["customer_creation"])
        workflow.add_node("fallback", fallback_node)

        workflow.add_conditional_edges(
            START,
            router_request,
            {
                "user_validation": "user_validation",
                "services_inquiry": "services_inquiry",
                "fallback": "fallback"
            },
        )
        workflow.add_conditional_edges(
            "user_validation",
            route_user_validation,
            {
                "customer_lookup": "customer_lookup",
                "customer_creation": "customer_creation",
                "end": END,
            },
        )
        workflow.add_edge("customer_lookup", END)
        workflow.add_edge("customer_creation", END)
        workflow.add_edge("services_inquiry", END)
        workflow.add_edge("fallback", END)

        self.graph = workflow.compile()


def router_request(state: UserValidationState) -> str:
    if state.get("next_action") in {
        "retry_customer_lookup",
        "retry_customer_creation",
    }:
        return "user_validation"

    if state.get("pending_question") in {
        "existing_customer_email",
        "confirm_create_customer",
        "new_customer_details",
    }:
        return "user_validation"

    if state.get("message_category") in {
        "new_appointment",
        "reschedule_appointment",
        "cancel_appointment",
    }:
        return "user_validation"

    if state.get("message_category") == "service_inquiry":
        return "services_inquiry"

    return "fallback"


def route_user_validation(state: UserValidationState) -> str:
    if state.get("next_action") == "lookup_customer":
        return "customer_lookup"

    if state.get("next_action") == "create_customer":
        return "customer_creation"

    return "end"

def fallback_node(state: UserValidationState) -> dict:
    return {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "Puedo ayudarte con citas, cambios o cancelaciones, "
                    "y preguntas sobre nuestros servicios. ¿Qué necesitas?"
                ),
            }
        ],
        "pending_question": None,
        "next_action": "clarify_intent",
    }

user_services_subgraph = UserServicesValidation().graph
