from .appointment_action_nodes import (
    book_appointment_node,
    cancel_appointment_node,
    check_availability_node,
    reschedule_appointment_node,
    view_appointment_node,
)
from .appointment_validation_node import appointment_validation_node

NODES = {
    "appointment_validation": appointment_validation_node,
    "book_appointment": book_appointment_node,
    "check_availability": check_availability_node,
    "reschedule_appointment": reschedule_appointment_node,
    "cancel_appointment": cancel_appointment_node,
    "view_appointment": view_appointment_node,
}
