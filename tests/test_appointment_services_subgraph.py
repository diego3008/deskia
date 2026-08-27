import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from langchain_core.messages import HumanMessage

from src.nodes.message_categorizer_node import message_categorizer_node
from src.nodes.user_services_validation.customer_creation_node import (
    customer_creation_node,
)
from src.nodes.user_services_validation.customer_lookup_node import customer_lookup_node


class JsonResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url):
        return self.response

    async def post(self, url, json):
        return self.response

    async def patch(self, url, json):
        return self.response


class ValidatedCustomerHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_publishes_customer_and_customer_id(self):
        customer_id = str(uuid4())
        FakeClient.response = JsonResponse(
            {"id": customer_id, "email": "ana@example.com"}
        )

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result.get("customer_id"), customer_id)
        self.assertEqual((result.get("customer") or {}).get("id"), customer_id)
        self.assertEqual(result["user_data"]["customer"]["id"], customer_id)

    async def test_creation_publishes_customer_and_customer_id(self):
        customer_id = str(uuid4())
        FakeClient.response = JsonResponse(
            {"id": customer_id, "email": "ana@example.com"}
        )

        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_creation_node(
                {
                    "business_id": uuid4(),
                    "user_data": {
                        "email": "ana@example.com",
                        "first_name": "Ana",
                        "last_name": "López",
                    },
                }
            )

        self.assertEqual(result.get("customer_id"), customer_id)
        self.assertEqual((result.get("customer") or {}).get("id"), customer_id)
        self.assertEqual(result["user_data"]["customer"]["id"], customer_id)

    async def test_lookup_retries_when_customer_id_is_missing(self):
        FakeClient.response = JsonResponse({"email": "ana@example.com"})

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result.get("next_action"), "retry_customer_lookup")

    async def test_creation_retries_when_customer_id_is_missing(self):
        FakeClient.response = JsonResponse({"email": "ana@example.com"})

        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            FakeClient,
        ):
            result = await customer_creation_node(
                {
                    "business_id": uuid4(),
                    "user_data": {
                        "email": "ana@example.com",
                        "first_name": "Ana",
                        "last_name": "López",
                    },
                }
            )

        self.assertEqual(result.get("next_action"), "retry_customer_creation")


class AppointmentServicesGraphTests(unittest.TestCase):
    def test_subgraph_compiles_as_a_tool_loop(self):
        from src.graph.appointment_services_subgraph import (
            appointment_services_subgraph,
        )

        graph = appointment_services_subgraph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn("appointment_agent", graph.nodes)
        self.assertIn("tools", graph.nodes)
        self.assertIn(("__start__", "appointment_agent"), edges)
        self.assertIn(("appointment_agent", "tools"), edges)
        self.assertIn(("tools", "appointment_agent"), edges)


class AppointmentContinuityRoutingTests(unittest.TestCase):
    @staticmethod
    def booking_module():
        from src.graph import appointment_booking_graph

        return appointment_booking_graph

    def test_new_appointment_without_customer_uses_validation(self):
        self.assertEqual(
            self.booking_module().route_by_category(
                {"message_category": "new_appointment"}
            ),
            "user_services",
        )

    def test_new_appointment_with_customer_enters_appointment_services(self):
        self.assertEqual(
            self.booking_module().route_by_category(
                {
                    "message_category": "new_appointment",
                    "customer_id": str(uuid4()),
                    "current_flow": "appointment_services",
                }
            ),
            "appointment_services",
        )

    def test_pending_customer_question_wins_over_appointment_flow(self):
        self.assertEqual(
            self.booking_module().route_by_category(
                {
                    "message_category": "confirmation",
                    "current_flow": "appointment_services",
                    "pending_question": "confirm_create_customer",
                }
            ),
            "user_services",
        )

    def test_validated_customer_handoff_enters_appointment_services(self):
        route_after_user_services = getattr(
            self.booking_module(), "route_after_user_services", None
        )
        self.assertIsNotNone(route_after_user_services)
        self.assertEqual(
            route_after_user_services(
                {
                    "current_flow": "appointment_services",
                    "customer_id": str(uuid4()),
                }
            ),
            "appointment_services",
        )

    def test_confirmation_continues_active_appointment_flow(self):
        self.assertEqual(
            self.booking_module().route_by_category(
                {
                    "message_category": "confirmation",
                    "current_flow": "appointment_services",
                    "customer_id": str(uuid4()),
                }
            ),
            "appointment_services",
        )

    def test_parent_graph_connects_both_subgraphs(self):
        graph = self.booking_module().booking_graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn("user_services", graph.nodes)
        self.assertIn("appointment_services", graph.nodes)
        self.assertIn(("user_services", "appointment_services"), edges)
        self.assertIn(("appointment_services", "message_writer"), edges)

    def test_categorizer_starts_appointment_flow(self):
        categorizer = SimpleNamespace(
            invoke=lambda inputs: SimpleNamespace(
                category=SimpleNamespace(value="new_appointment")
            )
        )
        incoming = HumanMessage(content="Quiero agendar una cita")

        with patch(
            "src.nodes.message_categorizer_node.message_categorizer_agent",
            return_value=categorizer,
        ):
            result = message_categorizer_node(
                {"current_message": incoming, "messages": [incoming]}
            )

        self.assertEqual(result.get("current_flow"), "appointment_services")

    def test_categorizer_clears_flow_on_topic_change(self):
        categorizer = SimpleNamespace(
            invoke=lambda inputs: SimpleNamespace(
                category=SimpleNamespace(value="greeting")
            )
        )
        incoming = HumanMessage(content="Hola")

        with patch(
            "src.nodes.message_categorizer_node.message_categorizer_agent",
            return_value=categorizer,
        ):
            result = message_categorizer_node(
                {
                    "current_message": incoming,
                    "messages": [incoming],
                    "current_flow": "appointment_services",
                    "active_appointment": {"id": "appointment-1"},
                    "confirmed_slot": {"starts_at": "2026-08-28T10:00:00"},
                }
            )

        self.assertIsNone(result.get("current_flow"))
        self.assertIsNone(result.get("active_appointment"))
        self.assertIsNone(result.get("confirmed_slot"))


if __name__ == "__main__":
    unittest.main()
