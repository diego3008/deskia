from src.nodes.message_categorizer_node import message_categorizer_node
from src.nodes.message_listener_node import message_listener_node as message_listener
from src.nodes.message_writer_node import message_writer_node

from .test_node import summarise, call_llm
from src.nodes.fallback_node import fallback_node

NODES = {
    "message_listener": message_listener,
    "message_categorizer": message_categorizer_node,
    "message_writer": message_writer_node,
    "fallback": fallback_node
}