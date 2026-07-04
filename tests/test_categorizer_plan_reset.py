from unittest.mock import MagicMock, patch

from src.nodes.message_categorizer_node import message_categorizer_node


def _mock_category(mock_factory, category):
    chain = MagicMock()
    result = MagicMock()
    result.category = MagicMock()
    result.category.value = category
    chain.invoke.return_value = result
    mock_factory.return_value = chain


def _state(**kw):
    base = {
        "current_message": "hi",
        "messages": [],
        "active_flow": "booking",
        "service_plan": {"intent": "book", "steps": ["availability", "book"]},
        "active_appointment": None,
        "confirmed_slot": None,
    }
    base.update(kw)
    return base


@patch("src.nodes.message_categorizer_node.message_categorizer_agent")
def test_service_plan_cleared_on_topic_change(mock_factory):
    _mock_category(mock_factory, "greeting")
    out = message_categorizer_node(_state())
    assert out["service_plan"] is None


@patch("src.nodes.message_categorizer_node.message_categorizer_agent")
def test_service_plan_cleared_on_fresh_service_request(mock_factory):
    _mock_category(mock_factory, "service_request")
    out = message_categorizer_node(
        _state(active_flow=None, current_message="I want to book Friday")
    )
    assert out["service_plan"] is None


@patch("src.nodes.message_categorizer_node.message_categorizer_agent")
def test_service_plan_kept_mid_flow_confirmation(mock_factory):
    _mock_category(mock_factory, "confirmation")
    plan = {"intent": "book", "steps": ["availability", "book"]}
    out = message_categorizer_node(
        _state(active_flow="booking", service_plan=plan, current_message="yes book it")
    )
    assert out["service_plan"] == plan
