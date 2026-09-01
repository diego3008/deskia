import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from src.nodes.compact_context_node import compact_context_node
from src.nodes.message_writer_node import message_writer_node


class FakeSummaryModel:
    def __init__(self, *args, **kwargs):
        pass

    def invoke(self, messages):
        return AIMessage(content="Customer wants a massage on Saturday.")


class FakeWriter:
    inputs = None

    def invoke(self, inputs):
        self.inputs = inputs
        return {"response": "Understood."}


class CompactContextTests(unittest.TestCase):
    def test_compacts_old_complete_turns_and_keeps_the_recent_tail(self):
        messages = [
            HumanMessage(content="old question", id="human-1"),
            AIMessage(content="old answer", id="ai-1"),
            HumanMessage(content="message 2", id="human-2"),
            AIMessage(content="answer 2", id="ai-2"),
            HumanMessage(content="message 3", id="human-3"),
            AIMessage(content="answer 3", id="ai-3"),
            HumanMessage(content="message 4", id="human-4"),
            AIMessage(content="answer 4", id="ai-4"),
        ]

        with (
            patch(
                "src.nodes.compact_context_node.ChatOpenRouter",
                FakeSummaryModel,
                create=True,
            ),
            patch(
                "src.nodes.compact_context_node.COMPACT_AT_TOKENS",
                1,
                create=True,
            ),
        ):
            result = compact_context_node(
                {"messages": messages, "conversation_summary": "Previous summary."}
            )

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["conversation_summary"],
            "Customer wants a massage on Saturday.",
        )
        self.assertEqual(
            [message.id for message in result["messages"] if isinstance(message, RemoveMessage)],
            ["human-1", "ai-1"],
        )

    @patch("src.nodes.message_writer_node.message_writer")
    def test_writer_receives_the_compacted_summary(self, writer_factory):
        writer = FakeWriter()
        writer_factory.return_value = writer

        message_writer_node(
            {
                "messages": [HumanMessage(content="latest", id="human-1")],
                "current_message": "latest",
                "message_category": "greeting",
                "conversation_summary": "Customer wants a massage on Saturday.",
            }
        )

        self.assertIn("Customer wants a massage on Saturday.", writer.inputs["conversation_history"])


if __name__ == "__main__":
    unittest.main()
