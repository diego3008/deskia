import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from src.graph.appointment_booking_graph import (
    booking_graph,
    route_after_message_writer,
    route_by_category,
)
from src.graph.user_services_validation_subgraph import router_request
from src.models.customers import CustomerCreate, CustomerInput
from src.nodes.user_services_validation.customer_creation_node import customer_creation_node
from src.nodes.user_services_validation.customer_lookup_node import customer_lookup_node
from src.nodes.user_services_validation.user_validation_node import user_validations_node
from src.nodes.message_listener_node import message_listener_node
from src.nodes.message_writer_node import message_writer_node
from src.structured_outputs import MessageCategory


class PendingQuestionFlowTests(unittest.TestCase):
    def test_writer_categories_route_to_message_writer(self):
        for category in {"greeting", "customer_complaint", "customer_feedback"}:
            self.assertEqual(route_by_category({"message_category": category}), "message_writer")

    def test_message_writer_routes_to_email_or_end(self):
        graph = booking_graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn("message_writer", graph.nodes)
        self.assertIn(("message_writer", "email_confirmation"), edges)
        self.assertIn(("message_writer", "__end__"), edges)
        self.assertEqual(route_after_message_writer({"message_category": "greeting"}), "end")

    def test_user_services_flows_to_message_writer(self):
        graph = booking_graph.get_graph()

        self.assertIn(
            ("user_services", "message_writer"),
            {(edge.source, edge.target) for edge in graph.edges},
        )

    def test_new_appointment_requests_customer_email(self):
        result = user_validations_node({"message_category": "new_appointment"})

        self.assertEqual(
            result,
            {
                "pending_question": "existing_customer_email",
                "next_action": "request_existing_customer_email",
                "user_data": {},
            },
        )

    def test_parent_routes_pending_reply_to_user_services(self):
        self.assertEqual(
            route_by_category(
                {
                    "pending_question": "existing_customer_email",
                    "message_category": "greeting",
                }
            ),
            "user_services",
        )

    def test_parent_routes_customer_retries_to_user_services(self):
        self.assertEqual(
            route_by_category(
                {"next_action": "retry_customer_lookup", "message_category": "greeting"}
            ),
            "user_services",
        )

    def test_child_routes_customer_retries_to_validation(self):
        self.assertEqual(
            router_request({"next_action": "retry_customer_creation"}),
            "user_validation",
        )

    def test_lookup_retry_restarts_lookup(self):
        result = user_validations_node({"next_action": "retry_customer_lookup"})

        self.assertEqual(result["next_action"], "lookup_customer")

    def test_creation_retry_restarts_creation(self):
        result = user_validations_node({"next_action": "retry_customer_creation"})

        self.assertEqual(result["next_action"], "create_customer")

    def test_email_reply_is_saved_before_customer_lookup(self):
        result = user_validations_node(
            {
                "pending_question": "existing_customer_email",
                "messages": [HumanMessage(content="ana@example.com")],
                "user_data": {},
            }
        )

        self.assertEqual(result["user_data"], {"email": "ana@example.com"})
        self.assertEqual(result["next_action"], "lookup_customer")

    def test_phrase_wrapped_email_is_saved_before_customer_lookup(self):
        result = user_validations_node(
            {
                "pending_question": "existing_customer_email",
                "messages": [HumanMessage(content="My email is ana@example.com, thanks.")],
                "user_data": {},
            }
        )

        self.assertEqual(result["user_data"], {"email": "ana@example.com"})
        self.assertEqual(result["next_action"], "lookup_customer")

    def test_invalid_email_reply_keeps_email_request_pending(self):
        result = user_validations_node(
            {
                "pending_question": "existing_customer_email",
                "messages": [HumanMessage(content="yes")],
                "user_data": {},
            }
        )

        self.assertEqual(result["pending_question"], "existing_customer_email")
        self.assertEqual(result["next_action"], "request_existing_customer_email")

    def test_newer_email_replaces_stale_customer_data(self):
        result = user_validations_node(
            {
                "pending_question": "existing_customer_email",
                "messages": [HumanMessage(content="new@example.com")],
                "user_data": {"email": "old@example.com", "customer": {"id": "old"}},
            }
        )

        self.assertEqual(
            result["user_data"],
            {"email": "new@example.com"},
        )

    def test_last_email_in_reply_replaces_previous_addresses(self):
        result = user_validations_node(
            {
                "pending_question": "existing_customer_email",
                "messages": [
                    HumanMessage(content="Use old@example.com instead of new@example.com")
                ],
                "user_data": {},
            }
        )

        self.assertEqual(result["user_data"], {"email": "new@example.com"})

    def test_new_booking_clears_customer_specific_data(self):
        result = user_validations_node(
            {
                "message_category": "new_appointment",
                "user_data": {"email": "old@example.com", "customer": {"id": "old"}},
            }
        )

        self.assertEqual(result["user_data"], {})
        self.assertEqual(result["pending_question"], "existing_customer_email")

    def test_confirmation_requests_new_customer_details(self):
        result = user_validations_node(
            {
                "pending_question": "confirm_create_customer",
                "message_category": "confirmation",
            }
        )

        self.assertEqual(result["pending_question"], "new_customer_details")
        self.assertEqual(result["next_action"], "request_new_customer_details")

    def test_full_name_reply_is_saved_before_customer_creation(self):
        result = user_validations_node(
            {
                "pending_question": "new_customer_details",
                "messages": [HumanMessage(content="Ana López")],
                "user_data": {"email": "ana@example.com"},
            }
        )

        self.assertEqual(
            result["user_data"],
            {
                "email": "ana@example.com",
                "first_name": "Ana",
                "last_name": "López",
            },
        )
        self.assertEqual(result["next_action"], "create_customer")

    def test_compound_surname_is_saved_before_customer_creation(self):
        result = user_validations_node(
            {
                "pending_question": "new_customer_details",
                "messages": [HumanMessage(content="Ana De la Cruz")],
                "user_data": {"email": "ana@example.com"},
            }
        )

        self.assertEqual(result["user_data"]["first_name"], "Ana")
        self.assertEqual(result["user_data"]["last_name"], "De la Cruz")
        self.assertEqual(result["next_action"], "create_customer")

    def test_name_prompt_prefix_is_removed_before_customer_creation(self):
        for message in ("My name is Ana López", "Mi nombre es Ana López"):
            with self.subTest(message=message):
                result = user_validations_node(
                    {
                        "pending_question": "new_customer_details",
                        "messages": [HumanMessage(content=message)],
                        "user_data": {"email": "ana@example.com"},
                    }
                )

                self.assertEqual(result["user_data"]["first_name"], "Ana")
                self.assertEqual(result["user_data"]["last_name"], "López")

    def test_invalid_customer_name_keeps_request_pending(self):
        result = user_validations_node(
            {
                "pending_question": "new_customer_details",
                "messages": [HumanMessage(content="   ")],
                "user_data": {"email": "ana@example.com"},
            }
        )

        self.assertEqual(result["pending_question"], "new_customer_details")
        self.assertEqual(result["next_action"], "request_new_customer_details")

    def test_customer_names_are_required_by_the_creation_model(self):
        with self.assertRaises(ValidationError):
            CustomerCreate(business_id=uuid4(), email="ana@example.com")

    def test_customer_input_names_are_required(self):
        with self.assertRaises(ValidationError):
            CustomerInput(email="ana@example.com")

    def test_removed_is_new_client_state_is_not_recognized(self):
        self.assertEqual(router_request({"pending_question": "is_new_client"}), "fallback")

    def test_reschedule_and_cancel_are_message_categories(self):
        self.assertEqual(MessageCategory.reschedule_appointment.value, "reschedule_appointment")
        self.assertEqual(MessageCategory.cancel_appointment.value, "cancel_appointment")


class MessageStateTests(unittest.TestCase):
    def test_listener_clears_the_previous_turn_response(self):
        incoming = HumanMessage(content="Quiero agendar una cita")
        state = {
            "messages": [incoming],
            "message_response": "Respuesta anterior",
        }

        result = message_listener_node(state)

        self.assertEqual(
            result,
            {
                "current_message": incoming,
                "message_response": "",
                "retrieved_services": "",
                "appointment_outcome": None,
                "email_draft": None,
                "email_confirmation": None,
            },
        )
        self.assertNotIn("current_message", state)
        self.assertEqual(state["message_response"], "Respuesta anterior")

    def test_writer_returns_only_the_new_message_delta(self):
        class FakeWriter:
            def invoke(self, inputs):
                return {"response": "¿En qué puedo ayudarte?"}

        incoming = HumanMessage(content="Hola")
        state = {
            "current_message": incoming,
            "message_category": "greeting",
            "messages": [incoming],
        }

        with patch(
            "src.nodes.message_writer_node.message_writer",
            return_value=FakeWriter(),
        ):
            result = message_writer_node(state)

        self.assertEqual(result["message_response"], "¿En qué puedo ayudarte?")
        self.assertEqual(len(result["messages"]), 1)
        self.assertIsInstance(result["messages"][0], AIMessage)
        self.assertEqual(result["messages"][0].content, "¿En qué puedo ayudarte?")
        self.assertEqual(state["messages"], [incoming])
        self.assertNotIn("message_response", state)

    def test_writer_passes_workflow_state_and_history_to_the_model(self):
        class FakeWriter:
            inputs = None

            def invoke(self, inputs):
                self.inputs = inputs
                return {"response": "¿Cuál es tu correo electrónico?"}

        writer = FakeWriter()
        incoming = HumanMessage(content="Quiero agendar una cita")
        state = {
            "current_message": incoming,
            "message_category": "new_appointment",
            "messages": [incoming],
            "pending_question": "existing_customer_email",
            "next_action": "request_existing_customer_email",
        }

        with patch(
            "src.nodes.message_writer_node.message_writer",
            return_value=writer,
        ):
            message_writer_node(state)

        self.assertEqual(
            {
                "workflow_context": writer.inputs.get("workflow_context"),
                "conversation_history": writer.inputs.get("conversation_history"),
            },
            {
                "workflow_context": (
                    "pending_question: existing_customer_email\n"
                    "next_action: request_existing_customer_email"
                ),
                "conversation_history": "User: Quiero agendar una cita",
            },
        )


class CustomerLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_not_found_requests_customer_creation_confirmation(self):
        class NotFoundResponse:
            status_code = 404

            def raise_for_status(self):
                raise AssertionError("404 responses should not raise before confirmation")

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def get(self, url):
                return NotFoundResponse()

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            return_value=FakeClient(),
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result["pending_question"], "confirm_create_customer")
        self.assertEqual(result["next_action"], "confirm_create_customer")

    async def test_http_status_error_requests_customer_lookup_retry(self):
        request = httpx.Request("GET", "https://example.com/customers/search")
        response = httpx.Response(500, request=request)

        class FailingResponse:
            status_code = 500

            def raise_for_status(self):
                raise httpx.HTTPStatusError("server error", request=request, response=response)

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def get(self, url):
                return FailingResponse()

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            return_value=FakeClient(),
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result["next_action"], "retry_customer_lookup")
        self.assertEqual(result["error"], "customer_lookup_failed")

    async def test_malformed_customer_lookup_response_requests_retry(self):
        class MalformedResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("invalid JSON")

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def get(self, url):
                return MalformedResponse()

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            return_value=FakeClient(),
        ):
            result = await customer_lookup_node(
                {"business_id": uuid4(), "user_data": {"email": "ana@example.com"}}
            )

        self.assertEqual(result["next_action"], "retry_customer_lookup")
        self.assertEqual(result["error"], "customer_lookup_failed")


class CustomerCreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_customer_creation_response_requests_retry(self):
        class MalformedResponse:
            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("invalid JSON")

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def post(self, url, json):
                return MalformedResponse()

        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            return_value=FakeClient(),
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

        self.assertEqual(result["next_action"], "retry_customer_creation")
        self.assertEqual(result["error"], "customer_creation_failed")


if __name__ == "__main__":
    unittest.main()
