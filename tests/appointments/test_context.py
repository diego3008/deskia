from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from src.nodes.appointments.context import (
    from_appointment_output,
    reset_appointment_state,
    to_appointment_input,
)
from src.structured_outputs import (
    AppointmentOperation,
    AppointmentPhase,
    ConfirmationStatus,
)


def _parent_state(**overrides):
    business_id = uuid4()
    customer_id = uuid4()
    history = [HumanMessage(content="I need to cancel my appointment")]
    base = {
        "business_id": business_id,
        "business_timezone": "America/Monterrey",
        "customer_id": customer_id,
        "current_message": "I need to cancel my appointment",
        "messages": history,
    }
    base.update(overrides)
    return base


def test_to_appointment_input_initializes_a_safe_private_state():
    parent = _parent_state()

    child = to_appointment_input(parent)

    assert child["business_id"] == parent["business_id"]
    assert child["business_timezone"] == "America/Monterrey"
    assert child["customer_id"] == parent["customer_id"]
    assert child["current_message"] == parent["current_message"]
    assert child["messages"] == parent["messages"]
    assert child["messages"] is not parent["messages"]
    assert child["message_history_length"] == 1
    assert child["phase"] == AppointmentPhase.COLLECTING
    assert child["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
    assert child["pending_action"] is None


def test_parent_context_overwrites_stale_context_embedded_in_appointment_state():
    parent = _parent_state(
        appointment={
            "operation": AppointmentOperation.CANCEL,
            "business_id": uuid4(),
            "business_timezone": "UTC",
            "customer_id": uuid4(),
            "current_message": "stale child message",
            "messages": [AIMessage(content="stale child history")],
            "message_history_length": 99,
        }
    )

    child = to_appointment_input(parent)

    assert child["operation"] == AppointmentOperation.CANCEL
    assert child["business_id"] == parent["business_id"]
    assert child["business_timezone"] == "America/Monterrey"
    assert child["customer_id"] == parent["customer_id"]
    assert child["current_message"] == parent["current_message"]
    assert child["messages"] == parent["messages"]
    assert child["message_history_length"] == 1


def test_from_appointment_output_returns_private_state_and_only_new_messages():
    parent = _parent_state()
    appointment_id = uuid4()
    requested_start = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
    child = to_appointment_input(parent)
    reply = AIMessage(content="Please confirm cancellation of your appointment.")
    child.update(
        {
            "operation": AppointmentOperation.CANCEL,
            "phase": AppointmentPhase.AWAITING_CONFIRMATION,
            "confirmation_status": ConfirmationStatus.PENDING,
            "selected_appointment": {"id": appointment_id},
            "requested_start": requested_start,
            "pending_action": {
                "action_id": uuid4(),
                "operation": AppointmentOperation.CANCEL,
                "appointment_id": appointment_id,
                "requested_start": requested_start,
            },
            "messages": parent["messages"] + [reply],
            "business_id": uuid4(),
            "customer_id": uuid4(),
            "customer": {"id": uuid4()},
            "active_flow": "other-flow",
        }
    )

    update = from_appointment_output(child)

    assert update["messages"] == [reply]
    assert update["appointment"]["operation"] == AppointmentOperation.CANCEL
    assert update["appointment"]["phase"] == AppointmentPhase.AWAITING_CONFIRMATION
    assert update["appointment"]["confirmation_status"] == ConfirmationStatus.PENDING
    assert update["appointment"]["selected_appointment"] == {"id": appointment_id}
    assert update["appointment"]["requested_start"] == requested_start
    assert update["appointment"]["pending_action"]["appointment_id"] == appointment_id
    assert "business_id" not in update
    assert "customer_id" not in update
    assert "customer" not in update
    assert "active_flow" not in update


def test_reset_appointment_state_clears_write_gates_without_a_legacy_confirmed_flag():
    state = reset_appointment_state()

    assert state["phase"] == AppointmentPhase.COLLECTING
    assert state["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
    assert state["selected_appointment"] is None
    assert state["availability_evidence"] is None
    assert state["pending_action"] is None
    assert "confirmed" not in state
