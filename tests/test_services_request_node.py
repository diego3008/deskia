from unittest.mock import MagicMock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from src.nodes.services_request_node import (
    services_request_node,
    SERVICES_REQUEST_SYSTEM_PROMPT,
)


def _capture_system(mock_llm_cls):
    captured = {}
    bound = MagicMock()

    def fake_invoke(messages, config=None):
        captured["system"] = messages[0].content
        return AIMessage(content="ok")

    bound.invoke.side_effect = fake_invoke
    mock_llm_cls.return_value.bind_tools.return_value = bound
    return captured


def _state(**kw):
    base = {
        "business_id": uuid4(),
        "messages": [HumanMessage(content="move my appointment to Monday")],
        "service_plan": None,
        "active_appointment": None,
        "confirmed_slot": None,
    }
    base.update(kw)
    return base


@patch("src.nodes.services_request_node.ChatAnthropic")
def test_prompt_is_unchanged_when_no_plan(mock_llm_cls):
    captured = _capture_system(mock_llm_cls)
    services_request_node(_state())
    assert captured["system"] == SERVICES_REQUEST_SYSTEM_PROMPT


@patch("src.nodes.services_request_node.ChatAnthropic")
def test_prompt_includes_plan_block_when_plan_present(mock_llm_cls):
    captured = _capture_system(mock_llm_cls)
    services_request_node(
        _state(
            service_plan={
                "intent": "reschedule",
                "steps": ["find", "availability", "reschedule"],
            }
        )
    )
    system = captured["system"]
    assert "CURRENT PLAN (reschedule)" in system
    assert "NEXT STEP: find" in system
    assert SERVICES_REQUEST_SYSTEM_PROMPT in system
