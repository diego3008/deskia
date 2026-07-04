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


from unittest.mock import MagicMock, patch

from src.nodes.services_planner_node import services_planner_node
from src.structured_outputs import BookingIntent


def _node_state(**kw):
    base = {
        "messages": [],
        "current_message": "I want to book Friday at 3pm",
        "service_plan": None,
        "active_appointment": None,
        "confirmed_slot": None,
    }
    base.update(kw)
    return base


def _mock_intent(mock_factory, intent):
    chain = MagicMock()
    result = MagicMock()
    result.intent = intent
    chain.invoke.return_value = result
    mock_factory.return_value = chain
    return chain


@patch("src.nodes.services_planner_node.services_planner_agent")
def test_planner_writes_plan_on_fresh_flow_per_intent(mock_factory):
    _mock_intent(mock_factory, BookingIntent.book)
    out = services_planner_node(_node_state())
    assert out == {"service_plan": {"intent": "book", "steps": ["availability", "book"]}}

    _mock_intent(mock_factory, BookingIntent.reschedule)
    out = services_planner_node(
        _node_state(current_message="move my appointment to Monday")
    )
    assert out == {
        "service_plan": {"intent": "reschedule", "steps": ["find", "availability", "reschedule"]}
    }


@patch("src.nodes.services_planner_node.services_planner_agent")
def test_planner_passthrough_when_plan_exists(mock_factory):
    out = services_planner_node(
        _node_state(service_plan={"intent": "book", "steps": ["availability", "book"]})
    )
    assert out == {}
    mock_factory.assert_not_called()


@patch("src.nodes.services_planner_node.services_planner_agent")
def test_planner_unknown_writes_no_plan(mock_factory):
    _mock_intent(mock_factory, BookingIntent.unknown)
    assert services_planner_node(_node_state(current_message="hmm")) == {}


@patch("src.nodes.services_planner_node.services_planner_agent")
def test_planner_degrades_on_error(mock_factory):
    chain = MagicMock()
    chain.invoke.side_effect = Exception("boom")
    mock_factory.return_value = chain
    assert services_planner_node(_node_state()) == {}
