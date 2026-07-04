from src.graph.services_graph import services_graph


def _edges():
    g = services_graph.get_graph()
    return {(e.source, e.target) for e in g.edges}


def test_planner_node_present():
    nodes = set(services_graph.get_graph().nodes.keys())
    assert "planner" in nodes
    assert "services_request_node" in nodes


def test_start_goes_to_planner_then_request_node():
    edges = _edges()
    assert ("__start__", "planner") in edges
    assert ("planner", "services_request_node") in edges
