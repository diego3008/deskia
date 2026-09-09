from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from src.helpers.workflow import clear_appointment_state, has_validated_customer
from src.nodes.appointment_services import NODES
from src.state import MessageGraphState
from src.structured_outputs import APPOINTMENT_CATEGORIES, APPOINTMENT_INTENTS


def _has_context(state: MessageGraphState) -> bool:
    return bool(state.get("business_id") and has_validated_customer(state))


def router_request(state: MessageGraphState) -> str:
    if _has_context(state) and (
        state.get("message_category") in APPOINTMENT_CATEGORIES
        or state.get("current_flow") == "appointment_services"
    ):
        return "appointment_validation"
    return "fallback"


def route_appointment_validation(state: MessageGraphState) -> str:
    action = state.get("next_action")
    return action if action in APPOINTMENT_INTENTS.values() else "fallback"


def fallback_node(state: MessageGraphState) -> dict:
    has_context = _has_context(state)
    message = (
        "¿Quieres agendar una cita, consultar horarios, reprogramar, cancelar o ver tus citas?"
        if has_context
        else "Necesito validar el negocio y el cliente antes de gestionar citas."
    )
    return {
        "messages": [AIMessage(content=message)],
        **clear_appointment_state(),
        "current_flow": "appointment_services" if has_context else None,
        "pending_question": "appointment_intent" if has_context else None,
        "next_action": "clarify_appointment_intent" if has_context else None,
    }


class AppointmentServicesSubgraph:
    def __init__(self):
        workflow = StateGraph(MessageGraphState)
        for name, node in NODES.items():
            workflow.add_node(name, node)
        workflow.add_node("fallback", fallback_node)
        workflow.add_conditional_edges(
            START,
            router_request,
            {"appointment_validation": "appointment_validation", "fallback": "fallback"},
        )
        workflow.add_conditional_edges(
            "appointment_validation",
            route_appointment_validation,
            {
                **{action: action for action in APPOINTMENT_INTENTS.values()},
                "fallback": "fallback",
            },
        )
        for action in APPOINTMENT_INTENTS.values():
            workflow.add_edge(action, END)
        workflow.add_edge("fallback", END)
        self.graph = workflow.compile()


appointment_services_subgraph = AppointmentServicesSubgraph().graph
