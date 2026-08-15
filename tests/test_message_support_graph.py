import pytest

from src.graph.message_support_graph import MessageSupportGraph, message_support_graph
from src.structured_outputs import MessageCategory


@pytest.mark.parametrize(
    "category",
    [
        MessageCategory.BOOK_APPOINTMENT,
        MessageCategory.CHECK_AVAILABILITY,
        MessageCategory.RESCHEDULE_APPOINTMENT,
        MessageCategory.CANCEL_APPOINTMENT,
        MessageCategory.VIEW_APPOINTMENT,
    ],
)
def test_appointment_categories_route_from_message_category(category):
    route = MessageSupportGraph().route_by_category(
        {"message_category": category.value}
    )

    assert route == "appointment_management"


@pytest.mark.parametrize(
    "category",
    [
        MessageCategory.GREETING,
        MessageCategory.SERVICE_INFORMATION,
        MessageCategory.SERVICE_DETAILS,
        MessageCategory.BUSINESS_INFORMATION,
    ],
)
def test_writer_categories_route_to_registered_writer_node(category):
    graph = MessageSupportGraph()
    route = graph.route_by_category({"message_category": category.value})

    assert route == "message_writer"
    assert route in message_support_graph.get_graph().nodes


@pytest.mark.parametrize(
    "category",
    [
        MessageCategory.PROVIDE_INFORMATION,
        MessageCategory.OUT_OF_SCOPE,
        MessageCategory.UNCLEAR,
        "not-a-category",
        None,
    ],
)
def test_unhandled_categories_route_to_registered_fallback_node(category):
    graph = MessageSupportGraph()
    route = graph.route_by_category({"message_category": category})

    assert route == "fallback_node"
    assert route in message_support_graph.get_graph().nodes


def test_parent_graph_exposes_all_category_destinations_and_terminal_paths():
    graph = message_support_graph.get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert ("category", "appointment_subgraph") in edges
    assert ("category", "message_writer") in edges
    assert ("category", "fallback_node") in edges
    assert ("message_writer", "__end__") in edges
    assert ("fallback_node", "__end__") in edges
    assert ("appointment_subgraph", "__end__") in edges
