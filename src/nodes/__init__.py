from src.nodes.message_categorizer_node import message_categorizer_node
from src.nodes.message_listener_node import message_listener_node as message_listener

from .test_node import summarise, call_llm


NODES = {
    "message_listener": message_listener,
    "message_categorizer": message_categorizer_node
}