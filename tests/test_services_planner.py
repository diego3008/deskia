from src.nodes.services_planner_node import (
    STEP_CATALOGS,
    plan_status,
    format_plan_block,
)


def _state(**kw):
    base = {
        "service_plan": None,
        "active_appointment": None,
        "confirmed_slot": None,
    }
    base.update(kw)
    return base


def _plan(intent):
    return {"intent": intent, "steps": STEP_CATALOGS[intent]}


def test_plan_status_no_plan_returns_empty():
    assert plan_status(_state()) == {"steps": [], "next": None}


def test_reschedule_next_advances_as_gates_are_satisfied():
    out = plan_status(_state(service_plan=_plan("reschedule")))
    assert out["next"] == "find"
    assert out["steps"][0] == {"id": "find", "status": "pending"}

    out = plan_status(
        _state(service_plan=_plan("reschedule"), active_appointment={"id": "a1"})
    )
    assert out["next"] == "availability"
    assert out["steps"][0] == {"id": "find", "status": "done"}

    out = plan_status(
        _state(
            service_plan=_plan("reschedule"),
            active_appointment={"id": "a1"},
            confirmed_slot={"starts_at": "2026-07-05T15:00:00"},
        )
    )
    assert out["next"] == "reschedule"


def test_booking_next_is_availability_then_book():
    assert plan_status(_state(service_plan=_plan("book")))["next"] == "availability"
    out = plan_status(
        _state(service_plan=_plan("book"), confirmed_slot={"starts_at": "x"})
    )
    assert out["next"] == "book"


def test_format_plan_block_marks_done_and_shows_next():
    plan = _plan("reschedule")
    status = plan_status(
        _state(service_plan=plan, active_appointment={"id": "a1"})
    )
    block = format_plan_block(plan, status)
    assert "reschedule" in block.lower()
    assert "[x] find" in block
    assert "[ ] availability" in block
    assert "NEXT STEP: availability" in block
