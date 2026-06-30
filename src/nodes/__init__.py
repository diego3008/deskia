from src.nodes.services_request_node import services_request_node
from src.nodes.enquiry_node import enquiry_node
from src.nodes.message_categorizer_node import message_categorizer_node
from src.nodes.message_listener_node import message_listener_node as message_listener
from src.nodes.message_writer_node import message_writer_node
from src.nodes.customer_node import customer_node

from src.nodes.fallback_node import fallback_node

NODES = {
    "message_listener": message_listener,
    "message_categorizer": message_categorizer_node,
    "message_writer": message_writer_node,
    "enquiry": enquiry_node,
    "customer": customer_node,
    "fallback": fallback_node
}

SERVICES_REQUEST_NODES = {
    "services_request_node": services_request_node,

    "fallback": fallback_node

}