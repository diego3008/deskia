from src.nodes.user_services_validation.customer_creation_node import customer_creation_node

from .customer_lookup_node import customer_lookup_node
from .services_inquiry_node import services_inquiry_node
from .user_validation_node import user_validations_node

NODES = {
    "user_validation": user_validations_node,
    "services_inquiry": services_inquiry_node,
    "customer_lookup": customer_lookup_node,
    "customer_creation": customer_creation_node
}
