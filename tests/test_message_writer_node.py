from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from src.nodes.message_writer_node import message_writer_node
from src.state import MessageGraphState


def _make_state(messages, current_message="hello", message_category="inquiry"):
    return MessageGraphState(
        messages=messages,
        current_message=current_message,
        message_category=message_category,
        message_response="",
    )


@patch("src.nodes.message_writer_node.message_writer")
def test_first_message_passes_is_first_true(mock_factory):
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {"response": "Hi! I'm Deskia. What can I do for you?"}
    mock_factory.return_value = mock_chain

    state = _make_state(messages=[HumanMessage(content="hello")])
    message_writer_node(state)

    mock_chain.invoke.assert_called_once_with({
        "message_content": "hello",
        "message_category": "inquiry",
        "is_first_message": True,
    })


@patch("src.nodes.message_writer_node.message_writer")
def test_subsequent_message_passes_is_first_false(mock_factory):
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {"response": "Let me help with that."}
    mock_factory.return_value = mock_chain

    state = _make_state(
        messages=[
            HumanMessage(content="hi"),
            AIMessage(content="Hi! I'm Deskia."),
            HumanMessage(content="I have a complaint"),
        ],
        current_message="I have a complaint",
        message_category="customer_complaint",
    )
    message_writer_node(state)

    mock_chain.invoke.assert_called_once_with({
        "message_content": "I have a complaint",
        "message_category": "customer_complaint",
        "is_first_message": False,
    })


@patch("src.nodes.message_writer_node.message_writer")
def test_node_writes_response_to_state(mock_factory):
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {"response": "Thanks for your feedback!"}
    mock_factory.return_value = mock_chain

    state = _make_state(messages=[HumanMessage(content="great product")])
    result = message_writer_node(state)

    assert result["message_response"] == "Thanks for your feedback!"
    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    assert any("Thanks for your feedback!" in m.content for m in ai_messages)
