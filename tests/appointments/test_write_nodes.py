import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.models.appointments import AppointmentCancellationResponse, AppointmentSummary
from src.nodes.appointments.write_nodes import (
    apply_confirmation,
    execute_book_node,
    execute_cancel_node,
    execute_reschedule_node,
    revalidate_pending_action,
    stage_pending_action,
)
from src.services.appointments import AppointmentApiError
from src.structured_outputs import AppointmentOperation, AppointmentPhase, ConfirmationStatus


BUSINESS_ID = UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_ID = UUID("22222222-2222-2222-2222-222222222222")
APPOINTMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
OLD_START = datetime(2026, 8, 19, 14, 30, tzinfo=timezone.utc)
START = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
END = datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc)


def _run(awaitable):
    return asyncio.run(awaitable)


class MutationClient:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    async def book(self, request):
        self.calls.append(("book", request))
        self._raise_if_needed()
        return _summary()

    async def reschedule(self, appointment_id, request):
        self.calls.append(("reschedule", appointment_id, request))
        self._raise_if_needed()
        return _summary()

    async def cancel(self, appointment_id, request):
        self.calls.append(("cancel", appointment_id, request))
        self._raise_if_needed()
        return AppointmentCancellationResponse(
            **{
                **_summary().model_dump(),
                "status": "cancelled",
                "active": False,
            },
            cancelled_at=START,
        )

    def _raise_if_needed(self):
        if self.error:
            raise self.error


def _summary():
    return AppointmentSummary(
        id=APPOINTMENT_ID,
        status="pending",
        starts_at=START,
        ends_at=END,
        active=True,
    )


def _state(operation):
    return {
        "business_id": BUSINESS_ID,
        "customer_id": CUSTOMER_ID,
        "operation": operation,
        "service_id": None,
        "cancellation_reason": "Customer requested cancellation",
        "requested_start": START,
        "requested_end": END,
        "selected_appointment": {
            "id": APPOINTMENT_ID,
            "starts_at": OLD_START,
            "ends_at": END,
            "status": "pending",
            "active": True,
        },
        "availability_evidence": {
            "starts_at": START,
            "ends_at": END,
            "service_id": None,
            "available": True,
        },
        "phase": AppointmentPhase.AWAITING_CONFIRMATION,
        "confirmation_status": ConfirmationStatus.PENDING,
        "confirmation_action_id": None,
    }


def _ready_state(operation):
    state = _state(operation)
    staged = stage_pending_action(state)
    state.update(staged)
    state["current_message"] = "yes"
    state.update(apply_confirmation(state))
    state.update(revalidate_pending_action(state))
    assert state["phase"] == AppointmentPhase.EXECUTING
    return state


@pytest.mark.parametrize(
    ("operation", "executor", "expected_call"),
    [
        (AppointmentOperation.BOOK, execute_book_node, "book"),
        (AppointmentOperation.RESCHEDULE, execute_reschedule_node, "reschedule"),
        (AppointmentOperation.CANCEL, execute_cancel_node, "cancel"),
    ],
)
def test_each_ready_action_performs_exactly_one_matching_mutation(operation, executor, expected_call):
    client = MutationClient()

    update = _run(executor(_ready_state(operation), client=client))

    assert [call[0] for call in client.calls] == [expected_call]
    assert update["phase"] == AppointmentPhase.SUCCEEDED
    assert update["pending_action"] is None
    assert update["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
    assert update["result"]["appointment"]["id"] == APPOINTMENT_ID


@pytest.mark.parametrize(
    ("operation", "executor"),
    [
        (AppointmentOperation.BOOK, execute_book_node),
        (AppointmentOperation.RESCHEDULE, execute_reschedule_node),
        (AppointmentOperation.CANCEL, execute_cancel_node),
    ],
)
def test_unapproved_or_stale_state_performs_zero_mutations(operation, executor):
    client = MutationClient()
    state = _ready_state(operation)
    state["confirmation_action_id"] = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    update = _run(executor(state, client=client))

    assert client.calls == []
    assert update["error"]["code"] == "stale_action"


def test_reschedule_refuses_an_unchanged_target_slot_without_a_mutation():
    client = MutationClient()
    state = _state(AppointmentOperation.RESCHEDULE)
    state["selected_appointment"] = {
        **state["selected_appointment"],
        "starts_at": START,
        "ends_at": END,
    }
    state.update(stage_pending_action(state))
    state["current_message"] = "yes"
    state.update(apply_confirmation(state))
    state.update(revalidate_pending_action(state))

    update = _run(execute_reschedule_node(state, client=client))

    assert client.calls == []
    assert update["error"]["code"] == "unchanged_slot"


@pytest.mark.parametrize(
    ("operation", "executor"),
    [
        (AppointmentOperation.BOOK, execute_book_node),
        (AppointmentOperation.RESCHEDULE, execute_reschedule_node),
        (AppointmentOperation.CANCEL, execute_cancel_node),
    ],
)
def test_api_failure_is_structured_and_never_retries_the_write(operation, executor):
    client = MutationClient(error=AppointmentApiError("conflict", "safe conflict", retryable=False))

    update = _run(executor(_ready_state(operation), client=client))

    assert len(client.calls) == 1
    assert update["phase"] == AppointmentPhase.FAILED
    assert update["error"]["code"] == "conflict"
    assert update["pending_action"] is None
