import asyncio
from datetime import datetime, timezone
from uuid import UUID

from src.graph.appointment_subgraph import build_appointment_graph
from src.models.appointments import AppointmentCancellationResponse, AppointmentSummary
from src.structured_outputs import AppointmentOperation, AppointmentPhase, ConfirmationStatus


BUSINESS_ID = UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_ID = UUID("22222222-2222-2222-2222-222222222222")
APPOINTMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
START = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
END = datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc)


def _run(awaitable):
    return asyncio.run(awaitable)


class Client:
    def __init__(self):
        self.calls = []

    async def list_customer_appointments(self, *args, **kwargs):
        self.calls.append("lookup")
        return [AppointmentSummary(id=APPOINTMENT_ID, status="pending", starts_at=START, ends_at=END, active=True)]

    async def cancel(self, appointment_id, request):
        self.calls.append("cancel")
        return AppointmentCancellationResponse(
            id=appointment_id,
            status="cancelled",
            starts_at=START,
            ends_at=END,
            cancelled_at=START,
        )

    async def check_availability(self, *args, **kwargs):
        raise AssertionError("cancel flow must not check availability")

    async def book(self, *args, **kwargs):
        raise AssertionError("cancel flow must not book")

    async def reschedule(self, *args, **kwargs):
        raise AssertionError("cancel flow must not reschedule")


def _state(**overrides):
    state = {
        "business_id": BUSINESS_ID,
        "business_timezone": "America/Monterrey",
        "customer_id": CUSTOMER_ID,
        "operation": AppointmentOperation.CANCEL,
        "phase": AppointmentPhase.COLLECTING,
        "confirmation_status": ConfirmationStatus.NOT_REQUESTED,
        "current_message": "Cancel my appointment",
        "messages": [],
        "message_history_length": 0,
    }
    state.update(overrides)
    return state


def test_cancel_graph_requires_confirmation_before_the_single_cancel_call():
    client = Client()
    graph = build_appointment_graph(client=client)

    first = _run(graph.ainvoke(_state()))

    assert client.calls == ["lookup"]
    assert first["phase"] == AppointmentPhase.AWAITING_CONFIRMATION
    assert first["pending_action"]["appointment_id"] == APPOINTMENT_ID

    second_state = {**first, "current_message": "yes", "messages": first["messages"], "message_history_length": len(first["messages"])}
    second = _run(graph.ainvoke(second_state))

    assert client.calls == ["lookup", "cancel"]
    assert second["phase"] == AppointmentPhase.SUCCEEDED
    assert second["pending_action"] is None
