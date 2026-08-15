from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.nodes.appointments.write_nodes import (
    apply_confirmation,
    classify_confirmation,
    clear_pending_action,
    revalidate_pending_action,
    stage_pending_action,
)
from src.structured_outputs import (
    AppointmentOperation,
    AppointmentPhase,
    ConfirmationStatus,
)


BUSINESS_ID = UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_ID = UUID("22222222-2222-2222-2222-222222222222")
APPOINTMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
START = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
END = datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc)


def _state(operation=AppointmentOperation.BOOK, **overrides):
    state = {
        "business_id": BUSINESS_ID,
        "customer_id": CUSTOMER_ID,
        "operation": operation,
        "service_id": None,
        "cancellation_reason": "Customer requested cancellation",
        "requested_start": START,
        "requested_end": END,
        "selected_appointment": {
            "id": APPOINTMENT_ID,
            "starts_at": START,
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
        "confirmation_status": ConfirmationStatus.NOT_REQUESTED,
        "confirmation_action_id": None,
        "phase": AppointmentPhase.AWAITING_CONFIRMATION,
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    "operation",
    [AppointmentOperation.BOOK, AppointmentOperation.RESCHEDULE, AppointmentOperation.CANCEL],
)
def test_stage_pending_action_creates_an_immutable_snapshot_and_exact_confirmation(operation):
    state = _state(operation)

    update = stage_pending_action(state)
    pending = update["pending_action"]

    assert pending["operation"] == operation
    assert pending["business_id"] == BUSINESS_ID
    assert pending["customer_id"] == CUSTOMER_ID
    assert pending["requested_start"] == START
    assert pending["cancellation_reason"] == "Customer requested cancellation"
    assert update["phase"] == AppointmentPhase.AWAITING_CONFIRMATION
    assert update["confirmation_status"] == ConfirmationStatus.PENDING
    assert update["confirmation_action_id"] is None
    assert START.isoformat() in update["messages"][0].content
    state["requested_start"] = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    assert pending["requested_start"] == START


def test_stage_refuses_to_create_a_write_action_without_fresh_matching_availability():
    update = stage_pending_action(
        _state(availability_evidence={"starts_at": START, "ends_at": END, "available": False})
    )

    assert update["pending_action"] is None
    assert update["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
    assert update["error"]["code"] == "availability_required"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yes", "approve"),
        ("Sí, confirmo", "approve"),
        ("confirm", "approve"),
        ("no", "reject"),
        ("No confirmo", "reject"),
        ("cancelar", "reject"),
        ("maybe", "unclear"),
        ("", "unclear"),
    ],
)
def test_confirmation_classification_is_explicit_and_fail_closed(text, expected):
    assert classify_confirmation(text) == expected


def test_ambiguous_confirmation_keeps_the_same_pending_action_without_executing():
    staged = stage_pending_action(_state())
    state = _state(
        pending_action=staged["pending_action"],
        confirmation_status=ConfirmationStatus.PENDING,
        current_message="maybe",
    )

    update = apply_confirmation(state)

    assert update["pending_action"] == staged["pending_action"]
    assert update["confirmation_status"] == ConfirmationStatus.PENDING
    assert update["confirmation_action_id"] is None
    assert update["phase"] == AppointmentPhase.AWAITING_CONFIRMATION


def test_rejection_clears_the_pending_action():
    staged = stage_pending_action(_state())
    state = _state(
        pending_action=staged["pending_action"],
        confirmation_status=ConfirmationStatus.PENDING,
        current_message="no",
    )

    update = apply_confirmation(state)

    assert update["pending_action"] is None
    assert update["confirmation_status"] == ConfirmationStatus.REJECTED
    assert update["confirmation_action_id"] is None
    assert update["phase"] == AppointmentPhase.COLLECTING


def test_confirmation_outside_the_awaiting_phase_fails_closed():
    staged = stage_pending_action(_state())

    update = apply_confirmation(
        _state(
            pending_action=staged["pending_action"],
            confirmation_status=ConfirmationStatus.PENDING,
            phase=AppointmentPhase.COLLECTING,
            current_message="yes",
        )
    )

    assert update["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
    assert update["error"]["code"] == "confirmation_not_pending"


def test_approved_matching_snapshot_is_the_only_path_to_execution():
    staged = stage_pending_action(_state())
    approved = apply_confirmation(
        _state(
            pending_action=staged["pending_action"],
            confirmation_status=ConfirmationStatus.PENDING,
            current_message="yes",
        )
    )
    state = _state(
        pending_action=staged["pending_action"],
        confirmation_status=approved["confirmation_status"],
        confirmation_action_id=approved["confirmation_action_id"],
    )

    update = revalidate_pending_action(state)

    assert update == {"phase": AppointmentPhase.EXECUTING, "error": None}


def test_approval_for_a_different_action_id_cannot_reach_execution():
    staged = stage_pending_action(_state())
    state = _state(
        pending_action=staged["pending_action"],
        confirmation_status=ConfirmationStatus.APPROVED,
        confirmation_action_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
    )

    update = revalidate_pending_action(state)

    assert update["phase"] == AppointmentPhase.COLLECTING
    assert update["pending_action"] is None
    assert update["error"]["code"] == "stale_action"


@pytest.mark.parametrize(
    "field,value",
    [
        ("business_id", UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        ("customer_id", UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        ("requested_start", datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)),
        ("service_id", UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
        ("selected_appointment", {"id": UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")}),
    ],
)
def test_changed_state_invalidates_an_approved_pending_action(field, value):
    staged = stage_pending_action(_state(AppointmentOperation.RESCHEDULE))
    state = _state(
        AppointmentOperation.RESCHEDULE,
        pending_action=deepcopy(staged["pending_action"]),
        confirmation_status=ConfirmationStatus.APPROVED,
    )
    state[field] = value

    update = revalidate_pending_action(state)

    assert update["phase"] == AppointmentPhase.COLLECTING
    assert update["pending_action"] is None
    assert update["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
    assert update["error"]["code"] == "stale_action"


def test_clear_pending_action_removes_any_approval_before_a_future_write():
    staged = stage_pending_action(_state())

    update = clear_pending_action(staged["pending_action"])

    assert update["pending_action"] is None
    assert update["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
