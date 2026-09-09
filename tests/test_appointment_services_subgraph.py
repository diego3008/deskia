import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from src.models.appointments import AppointmentInput
from src.nodes.message_categorizer_node import message_categorizer_node
from src.nodes.message_writer_node import message_writer_node
from src.nodes.tools.services.services_tools import (
    create_appointment,
    reschedule_appointment,
)
from src.nodes.user_services_validation.customer_creation_node import (
    customer_creation_node,
)
from src.nodes.user_services_validation.customer_lookup_node import customer_lookup_node


APPOINTMENT_CASES = {
    "new_appointment": "book_appointment",
    "check_availability": "check_availability",
    "reschedule_appointment": "reschedule_appointment",
    "cancel_appointment": "cancel_appointment",
    "view_appointment": "view_appointment",
}


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

    async def test_lookup_retries_when_payload_is_not_an_object(self):
        FakeClient.response = JsonResponse([])

        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
            FakeClient,
        ):
            try:
                result = await customer_lookup_node(
                    {
                        "business_id": uuid4(),
                        "user_data": {"email": "ana@example.com"},
                    }
                )
            except Exception as error:
                self.fail(f"lookup raised instead of returning retry state: {error}")

        self.assertEqual(result.get("next_action"), "retry_customer_lookup")

    async def test_creation_retries_when_payload_is_not_an_object(self):
        FakeClient.response = JsonResponse(None)

        with patch(
            "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
            FakeClient,
        ):
            try:
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
            except Exception as error:
                self.fail(f"creation raised instead of returning retry state: {error}")

        self.assertEqual(result.get("next_action"), "retry_customer_creation")


    async def test_all_intents_survive_compiled_customer_lookup(self):
        from src.graph.user_services_validation_subgraph import user_services_subgraph
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        from src.graph.appointment_booking_graph import route_after_user_services
        FakeClient.response = JsonResponse({"id": "customer-1", "email": "ana@example.com"})
        for intent in APPOINTMENT_CASES.values():
            with self.subTest(intent=intent), patch(
                "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient",
                FakeClient,
            ):
                result = await user_services_subgraph.ainvoke({
                    "messages": [HumanMessage(content="ana@example.com")],
                    "business_id": uuid4(), "message_category": "unrelated",
                    "current_flow": "appointment_services", "appointment_intent": intent,
                    "pending_question": "existing_customer_email",
                })
            self.assertEqual(result["appointment_intent"], intent)
            self.assertEqual(route_after_user_services(result), "appointment_services")
            final = await appointment_services_subgraph.ainvoke(result)
            self.assertIn("pendiente", final["messages"][-1].content)
            self.assertIsNone(final["appointment_intent"])

    async def test_intent_survives_creation_confirmation_and_details(self):
        from src.graph.user_services_validation_subgraph import user_services_subgraph
        for intent in APPOINTMENT_CASES.values():
            result = await user_services_subgraph.ainvoke({
                "messages": [HumanMessage(content="Sí")],
                "business_id": uuid4(), "message_category": "confirmation",
                "current_flow": "appointment_services", "appointment_intent": intent,
                "pending_question": "confirm_create_customer",
                "user_data": {"email": "ana@example.com"},
            })
            self.assertEqual(result["pending_question"], "new_customer_details")
            self.assertEqual(result["appointment_intent"], intent)
            FakeClient.response = JsonResponse({"id": "customer-1", "email": "ana@example.com"})
            with patch(
                "src.nodes.user_services_validation.customer_creation_node.httpx.AsyncClient",
                FakeClient,
            ):
                result = await user_services_subgraph.ainvoke({
                    **result, "messages": [HumanMessage(content="Ana López")],
                })
            self.assertEqual(result["appointment_intent"], intent)
            self.assertEqual(result["customer_id"], "customer-1")


class CustomerValidationHandoffRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_pending_identity_blocks_handoff_with_cached_customer(self):
        from src.graph.appointment_booking_graph import route_after_user_services

        for identity in ({"customer_id": "customer-1"}, {"customer": {"id": "customer-1"}}):
            for pending in (
                {"pending_question": "existing_customer_email"},
                {"pending_question": "confirm_create_customer"},
                {"pending_question": "new_customer_details"},
                {"next_action": "retry_customer_lookup"},
                {"next_action": "retry_customer_creation"},
            ):
                with self.subTest(identity=identity, pending=pending):
                    self.assertEqual(route_after_user_services({
                        "current_flow": "appointment_services", **identity, **pending,
                    }), "message_writer")

    async def test_repeated_failed_lookup_preserves_retry_in_parent(self):
        from src.graph.appointment_booking_graph import booking_graph

        FakeClient.response = JsonResponse([])
        state = {
            "business_id": uuid4(), "customer_id": "customer-1",
            "current_flow": "appointment_services", "appointment_intent": "view_appointment",
            "next_action": "retry_customer_lookup", "user_data": {"email": "ana@example.com"},
        }
        with patch(
            "src.nodes.user_services_validation.customer_lookup_node.httpx.AsyncClient", FakeClient,
        ), patch(
            "src.nodes.message_categorizer_node.message_categorizer_agent",
        ) as categorizer, patch(
            "src.nodes.message_writer_node.message_writer",
        ) as writer:
            categorizer.return_value.invoke.return_value = SimpleNamespace(
                category=SimpleNamespace(value="view_appointment"),
            )
            writer.return_value.invoke.return_value = {"response": "Necesito reintentar la búsqueda."}
            for _ in range(2):
                state = await booking_graph.ainvoke({
                    **state, "messages": [HumanMessage(content="Quiero ver mi cita")],
                })
                self.assertEqual(state["next_action"], "retry_customer_lookup")
                self.assertEqual(state["appointment_intent"], "view_appointment")
                self.assertEqual(state["current_flow"], "appointment_services")
                self.assertEqual(state["customer_id"], "customer-1")
                self.assertEqual(state["message_response"], "Necesito reintentar la búsqueda.")


class AppointmentIntentTests(unittest.TestCase):
    def categorize(self, category, **state):
        message = HumanMessage(content="Solicitud de prueba")
        agent = SimpleNamespace(invoke=lambda inputs: SimpleNamespace(
            category=SimpleNamespace(value=category)))
        with patch(
            "src.nodes.message_categorizer_node.message_categorizer_agent",
            return_value=agent,
        ):
            return message_categorizer_node({
                **state, "current_message": message, "messages": [message],
            })

    def test_all_actions_and_identity_continuity(self):
        from src.structured_outputs import MessageCategory
        for category, intent in APPOINTMENT_CASES.items():
            with self.subTest(category=category):
                self.assertEqual(MessageCategory(category).value, category)
                result = self.categorize(category)
                self.assertEqual(result["appointment_intent"], intent)
                self.assertEqual(result["current_flow"], "appointment_services")
                result = self.categorize("confirmation", **result)
                self.assertEqual(result["appointment_intent"], intent)

    def test_switch_preserves_customer_question_but_clears_slot(self):
        result = self.categorize(
            "cancel_appointment", appointment_intent="book_appointment",
            current_flow="appointment_services",
            pending_question="existing_customer_email",
            next_action="request_existing_customer_email",
            confirmed_slot={"starts_at": "2026-09-10T10:00:00"},
            active_appointment={"id": "old"},
        )
        self.assertEqual(result["appointment_intent"], "cancel_appointment")
        self.assertEqual(result["pending_question"], "existing_customer_email")
        self.assertIsNone(result["confirmed_slot"])
        self.assertIsNone(result["active_appointment"])

    def test_decline_and_service_inquiry_clear_intent(self):
        for category in ("decline", "service_inquiry", "greeting"):
            result = self.categorize(
                category, appointment_intent="cancel_appointment",
                current_flow="appointment_services",
            )
            self.assertIsNone(result["appointment_intent"])
            self.assertIsNone(result["current_flow"])

    def test_ambiguous_request_does_not_reuse_the_previous_action(self):
        result = self.categorize(
            "service_request", appointment_intent="cancel_appointment",
            current_flow="appointment_services", next_action="cancel_appointment",
            confirmed_slot={"starts_at": "stale"},
        )
        self.assertIsNone(result["appointment_intent"])
        self.assertIsNone(result["next_action"])
        self.assertIsNone(result["confirmed_slot"])


class AppointmentExplicitGraphTests(unittest.TestCase):
    def test_actions_are_terminal_and_do_not_consume_apis(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        from src.graph.appointment_booking_graph import route_after_message_writer
        graph = appointment_services_subgraph.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}
        self.assertNotIn("tools", graph.nodes)
        self.assertNotIn("appointment_agent", graph.nodes)
        self.assertIn("appointment_validation", graph.nodes)
        for category, action in APPOINTMENT_CASES.items():
            with self.subTest(action=action), patch(
                "httpx.AsyncClient", side_effect=AssertionError("Unexpected HTTP")
            ), patch(
                "langchain_openrouter.ChatOpenRouter",
                side_effect=AssertionError("Unexpected appointment LLM"),
            ):
                self.assertIn((action, "__end__"), edges)
                result = appointment_services_subgraph.invoke({
                    "messages": [HumanMessage(content="Solicitud")],
                    "message_category": category,
                    "business_id": str(uuid4()), "customer_id": "customer-1",
                    "current_flow": "appointment_services",
                    "confirmed_slot": {"starts_at": "stale"},
                    "active_appointment": {"id": "stale"},
                })
                self.assertIsInstance(result["messages"][-1], AIMessage)
                self.assertIn("pendiente", result["messages"][-1].content)
                expected_phrase = {
                    "book_appointment": "agendar citas",
                    "check_availability": "consultar horarios",
                    "reschedule_appointment": "reprogramar citas",
                    "cancel_appointment": "cancelar citas",
                    "view_appointment": "consultar tus citas",
                }[action]
                self.assertIn(expected_phrase, result["messages"][-1].content)
                self.assertEqual(result["customer_id"], "customer-1")
                for field in ("appointment_intent", "current_flow", "next_action",
                              "pending_question", "confirmed_slot", "active_appointment"):
                    self.assertIsNone(result[field])
                self.assertIsNone(result["appointment_outcome"])
                self.assertEqual(route_after_message_writer(result), "end")

    def test_validation_rejects_stale_intent_and_contextless_confirmation(self):
        from src.nodes.appointment_services.appointment_validation_node import (
            appointment_validation_node,
        )
        for category in ("unrelated", "", "not_a_category", "confirmation"):
            state = {"message_category": category,
                     "appointment_intent": "book_appointment",
                     "next_action": "book_appointment"}
            self.assertEqual(appointment_validation_node(state)["next_action"],
                             "clarify_appointment_intent")
        for category, intent in (
            ("unrelated", "book_appointment"),
            ("", "book_appointment"),
            ("not_a_category", "book_appointment"),
            ("service_request", "book_appointment"),
            ("confirmation", "not_an_intent"),
        ):
            with self.subTest(category=category, intent=intent):
                result = appointment_validation_node({
                    "message_category": category, "appointment_intent": intent,
                    "current_flow": "appointment_services", "next_action": "book_appointment",
                })
                self.assertEqual(result["next_action"], "clarify_appointment_intent")
                self.assertIsNone(result["appointment_intent"])
        result = appointment_validation_node({
            "message_category": "confirmation", "appointment_intent": "view_appointment",
            "current_flow": "appointment_services",
        })
        self.assertEqual(result["next_action"], "view_appointment")

    def test_unknown_intent_clarifies_and_missing_identity_terminates(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        base = {"messages": [HumanMessage(content="Sí")],
                "message_category": "confirmation", "current_flow": "appointment_services",
                "business_id": str(uuid4()), "customer_id": "customer-1"}
        result = appointment_services_subgraph.invoke(base)
        self.assertEqual(result["pending_question"], "appointment_intent")
        self.assertEqual(result["next_action"], "clarify_appointment_intent")
        for missing in ("business_id", "customer_id"):
            result = appointment_services_subgraph.invoke({
                **base, missing: None, "message_category": "cancel_appointment",
            })
            self.assertIsNone(result["current_flow"])
            self.assertIn("validar", result["messages"][-1].content)


class AppointmentExpandedRoutingTests(unittest.TestCase):
    def test_action_switch_does_not_answer_customer_questions(self):
        from src.nodes.user_services_validation.user_validation_node import user_validations_node

        for question, action in (
            ("existing_customer_email", "request_existing_customer_email"),
            ("confirm_create_customer", "confirm_create_customer"),
            ("new_customer_details", "request_new_customer_details"),
        ):
            with self.subTest(question=question):
                result = user_validations_node({
                    "message_category": "cancel_appointment",
                    "pending_question": question,
                    "messages": [HumanMessage(content="Cancela mi cita")],
                    "user_data": {"email": "ana@example.com"},
                })
                self.assertEqual(result["pending_question"], question)
                self.assertEqual(result["next_action"], action)
                self.assertNotIn("user_data", result)

    def test_every_category_enters_identification_then_appointment_services(self):
        from src.graph.appointment_booking_graph import route_by_category, route_after_user_services
        from src.graph.user_services_validation_subgraph import router_request
        from src.nodes.user_services_validation.user_validation_node import user_validations_node
        for category in (*APPOINTMENT_CASES, "service_request"):
            with self.subTest(category=category):
                state = {"message_category": category,
                         "current_flow": "appointment_services",
                         "appointment_intent": APPOINTMENT_CASES.get(category)}
                self.assertEqual(route_by_category(state), "user_services")
                self.assertEqual(router_request(state), "user_validation")
                self.assertEqual(user_validations_node(state)["pending_question"],
                                 "existing_customer_email")
                validated = {**state, "customer": {"id": "customer-1"}}
                self.assertEqual(route_by_category(validated), "appointment_services")
                self.assertEqual(route_after_user_services(validated), "appointment_services")

    def test_customer_retry_still_wins_with_a_validated_customer(self):
        from src.graph.appointment_booking_graph import route_by_category
        self.assertEqual(route_by_category({
            "message_category": "view_appointment", "customer_id": "customer-1",
            "next_action": "retry_customer_lookup",
        }), "user_services")

    def test_pending_response_reaches_writer_unchanged(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        result = appointment_services_subgraph.invoke({
            "messages": [HumanMessage(content="Cancela mi cita")],
            "message_category": "cancel_appointment",
            "business_id": str(uuid4()), "customer_id": "customer-1",
        })
        with patch("src.nodes.message_writer_node.message_writer") as model:
            written = message_writer_node(result)
        model.assert_not_called()
        self.assertEqual(written["message_response"],
            "La integración para cancelar citas está pendiente. No he cancelado ninguna cita.")
        self.assertNotIn("messages", written)

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

    def test_decline_clears_pending_customer_validation(self):
        categorizer = SimpleNamespace(
            invoke=lambda inputs: SimpleNamespace(
                category=SimpleNamespace(value="decline")
            )
        )
        incoming = HumanMessage(content="No, gracias")

        for pending_question, next_action in (
            ("existing_customer_email", "request_existing_customer_email"),
            ("new_customer_details", "request_new_customer_details"),
        ):
            with self.subTest(pending_question=pending_question):
                state = {
                    "current_message": incoming,
                    "messages": [incoming],
                    "current_flow": "appointment_services",
                    "pending_question": pending_question,
                    "next_action": next_action,
                }
                with patch(
                    "src.nodes.message_categorizer_node.message_categorizer_agent",
                    return_value=categorizer,
                ):
                    result = message_categorizer_node(state)

                self.assertIsNone(result.get("pending_question"))
                self.assertIsNone(result.get("next_action"))
                self.assertEqual(
                    self.booking_module().route_by_category(result),
                    "message_writer",
                )


class AppointmentResponseHandoffTests(unittest.TestCase):
    def test_writer_reuses_final_appointment_agent_message(self):
        incoming = HumanMessage(content="Quiero agendar una cita")
        final = AIMessage(content="Tu cita quedó agendada para mañana a las 10.")

        with patch("src.nodes.message_writer_node.message_writer") as writer:
            result = message_writer_node(
                {
                    "current_message": incoming,
                    "message_category": "new_appointment",
                    "messages": [incoming, final],
                }
            )

        writer.assert_not_called()
        self.assertEqual(result.get("message_response"), final.content)
        self.assertNotIn("messages", result)


class AppointmentToolLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_completion_clears_flow(self):
        start = datetime.fromisoformat("2026-08-28T10:00:00")
        FakeClient.response = JsonResponse({"id": str(uuid4())})
        state = {
            "business_id": uuid4(),
            "customer_id": str(uuid4()),
            "current_flow": "appointment_services",
            "next_action": "collect_appointment_details",
            "confirmed_slot": {"starts_at": start.isoformat()},
        }

        with patch(
            "src.nodes.tools.services.services_tools.httpx.AsyncClient",
            FakeClient,
        ):
            command = await create_appointment.coroutine(
                AppointmentInput(
                    starts_at=start,
                    ends_at=start + timedelta(hours=1),
                ),
                "tool-create",
                state,
            )

        for field in ("current_flow", "next_action", "pending_question"):
            self.assertIn(field, command.update)
            self.assertIsNone(command.update[field])

    async def test_reschedule_completion_clears_flow(self):
        start = datetime.fromisoformat("2026-08-29T11:00:00")
        FakeClient.response = JsonResponse({"id": str(uuid4())})
        state = {
            "business_id": uuid4(),
            "current_flow": "appointment_services",
            "next_action": "collect_appointment_details",
            "active_appointment": {"id": str(uuid4())},
            "confirmed_slot": {"starts_at": start.isoformat()},
        }

        with patch(
            "src.nodes.tools.services.services_tools.httpx.AsyncClient",
            FakeClient,
        ):
            command = await reschedule_appointment.coroutine(
                AppointmentInput(
                    starts_at=start,
                    ends_at=start + timedelta(hours=1),
                ),
                "tool-reschedule",
                state,
            )

        for field in ("current_flow", "next_action", "pending_question"):
            self.assertIn(field, command.update)
            self.assertIsNone(command.update[field])


if __name__ == "__main__":
    unittest.main()
