
import os
from functools import partial

from langgraph.graph import END, START, StateGraph

from src.nodes.appointments.context import from_appointment_output, reset_appointment_state, to_appointment_input
from src.nodes.appointments.flow_nodes import extract_appointment_details_node, fallback_appointment_node
from src.nodes.appointments.read_nodes import check_availability_node, lookup_appointments_node
from src.nodes.appointments.response_nodes import availability_response_node, lookup_response_node
from src.nodes.appointments.write_nodes import apply_confirmation, execute_book_node, execute_cancel_node, execute_reschedule_node, revalidate_pending_action, stage_pending_action
from src.services.appointments import AppointmentApiClient
from src.state import AppointmentState, MessageGraphState
from src.structured_outputs import AppointmentOperation, AppointmentPhase, ConfirmationStatus, MessageCategory

CATEGORY_OPERATIONS = {
    MessageCategory.BOOK_APPOINTMENT: AppointmentOperation.BOOK,
    MessageCategory.CHECK_AVAILABILITY: AppointmentOperation.CHECK_AVAILABILITY,
    MessageCategory.RESCHEDULE_APPOINTMENT: AppointmentOperation.RESCHEDULE,
    MessageCategory.CANCEL_APPOINTMENT: AppointmentOperation.CANCEL,
    MessageCategory.VIEW_APPOINTMENT: AppointmentOperation.VIEW,
}


def _route_start(state: AppointmentState) -> str:
    if state.get("pending_action"):
        if state.get("confirmation_status") == ConfirmationStatus.PENDING:
            return "confirm"
        if state.get("confirmation_status") == ConfirmationStatus.APPROVED:
            return "revalidate"
    operation = state.get("operation")
    if operation == AppointmentOperation.BOOK:
        return "details"
    if operation == AppointmentOperation.CHECK_AVAILABILITY:
        return "details"
    if operation in {AppointmentOperation.RESCHEDULE, AppointmentOperation.CANCEL, AppointmentOperation.VIEW}:
        if operation == AppointmentOperation.RESCHEDULE and state.get("selected_appointment"):
            return "details"
        return "lookup"
    return "fallback"


def _route_after_details(state: AppointmentState) -> str:
    return "availability" if state.get("requested_start") and state.get("requested_end") else "end"


def _route_after_lookup(state: AppointmentState) -> str:
    if not state.get("selected_appointment"):
        return "lookup_response"
    if state.get("operation") == AppointmentOperation.CANCEL:
        return "stage"
    if state.get("operation") == AppointmentOperation.RESCHEDULE:
        return "details"
    return "lookup_response"


def _route_after_availability_response(state: AppointmentState) -> str:
    if state.get("availability_evidence", {}).get("available") is True and state.get("operation") in {AppointmentOperation.BOOK, AppointmentOperation.RESCHEDULE}:
        return "stage"
    return "end"


def _route_after_confirmation(state: AppointmentState) -> str:
    return "revalidate" if state.get("confirmation_status") == ConfirmationStatus.APPROVED else "end"


def _route_execution(state: AppointmentState) -> str:
    return {
        AppointmentOperation.BOOK: "book",
        AppointmentOperation.RESCHEDULE: "reschedule",
        AppointmentOperation.CANCEL: "cancel",
    }.get(state.get("operation"), "end")


def build_appointment_graph(*, client: AppointmentApiClient):
    """Compile the fixed appointment state machine with an explicit API client."""
    graph = StateGraph(AppointmentState)
    graph.add_node("details", extract_appointment_details_node)
    graph.add_node("availability", partial(check_availability_node, client=client))
    graph.add_node("availability_response", availability_response_node)
    graph.add_node("lookup", partial(lookup_appointments_node, client=client))
    graph.add_node("lookup_response", lookup_response_node)
    graph.add_node("stage", stage_pending_action)
    graph.add_node("confirm", apply_confirmation)
    graph.add_node("revalidate", revalidate_pending_action)
    graph.add_node("book", partial(execute_book_node, client=client))
    graph.add_node("reschedule", partial(execute_reschedule_node, client=client))
    graph.add_node("cancel", partial(execute_cancel_node, client=client))
    graph.add_node("fallback", fallback_appointment_node)
    graph.add_conditional_edges(START, _route_start)
    graph.add_conditional_edges("details", _route_after_details, {"availability": "availability", "end": END})
    graph.add_edge("availability", "availability_response")
    graph.add_conditional_edges("availability_response", _route_after_availability_response, {"stage": "stage", "end": END})
    graph.add_conditional_edges("lookup", _route_after_lookup)
    graph.add_edge("lookup_response", END)
    graph.add_edge("stage", END)
    graph.add_conditional_edges("confirm", _route_after_confirmation, {"revalidate": "revalidate", "end": END})
    graph.add_conditional_edges("revalidate", _route_execution, {"book": "book", "reschedule": "reschedule", "cancel": "cancel", "end": END})
    graph.add_edge("book", END)
    graph.add_edge("reschedule", END)
    graph.add_edge("cancel", END)
    graph.add_edge("fallback", END)
    return graph.compile()


def _runtime_client() -> AppointmentApiClient:
    base_url = os.getenv("DESKIA_API_URL")
    if not base_url:
        raise RuntimeError("DESKIA_API_URL must be configured for appointment operations")
    return AppointmentApiClient(base_url)


async def appointment_adapter(state: MessageGraphState) -> dict:
    child = to_appointment_input(state)
    try:
        category = MessageCategory(state.get("message_category"))
    except (ValueError, TypeError):
        category = None
    operation = CATEGORY_OPERATIONS.get(category)
    if operation is not None and child.get("operation") != operation:
        child.update(reset_appointment_state())
        child["operation"] = operation
    output = await build_appointment_graph(client=_runtime_client()).ainvoke(child)
    update = from_appointment_output(output)
    if output.get("phase") in {AppointmentPhase.SUCCEEDED, AppointmentPhase.FAILED}:
        update["active_flow"] = None
    return update
