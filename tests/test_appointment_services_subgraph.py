import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import patch
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, HumanMessage

from src.models.appointments import AppointmentInput
from src.helpers.workflow import clear_appointment_state
from src.nodes.message_categorizer_node import message_categorizer_node
from src.nodes.message_writer_node import message_writer_node
from src.nodes.tools.services.services_tools import (
    create_appointment,
    reschedule_appointment,
)
from src.nodes.tools.messages_tools import (
    create_appointment as create_message_appointment,
)
from src.nodes.user_services_validation.customer_creation_node import (
    customer_creation_node,
)
from src.nodes.user_services_validation.customer_lookup_node import customer_lookup_node
from src.state import MessageGraphState


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

    async def get(self, url, **kwargs):
        return self.response

    async def post(self, url, json):
        return self.response

    async def put(self, url, **kwargs):
        return self.response


class AppointmentStateContractTests(unittest.TestCase):
    def test_clear_appointment_state_clears_appointment_details(self):
        annotations = get_type_hints(MessageGraphState)
        self.assertEqual(annotations["starts_at"], datetime | None)
        self.assertEqual(annotations["ends_at"], datetime | None)
        self.assertEqual(annotations["service_name"], str | None)
        self.assertEqual(annotations["service_id"], UUID | str | None)
        self.assertEqual(annotations["business_staff_id"], UUID | str | None)

        cleared = clear_appointment_state()
        for field in (
            "starts_at",
            "ends_at",
            "service_name",
            "service_id",
            "business_staff_id",
        ):
            self.assertIsNone(cleared[field])


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
        from src.models.appointment_details import AppointmentDetails

        for intent in APPOINTMENT_CASES.values():
            FakeClient.response = JsonResponse(
                {"id": "customer-1", "email": "ana@example.com"}
            )
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
            if intent in {"book_appointment", "check_availability"}:
                agent = SimpleNamespace(invoke=lambda inputs: AppointmentDetails())
                with patch(
                    "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
                    return_value=agent,
                ):
                    final = await appointment_services_subgraph.ainvoke(result)
                self.assertEqual(final["pending_question"], "appointment_details")
                self.assertEqual(final["appointment_intent"], intent)
            else:
                FakeClient.response = JsonResponse(
                    {
                        "appointment_id": "appointment-1",
                        "starts_at": "2026-09-18T10:00:00-06:00",
                        "service_name": "Corte de cabello",
                        "staff_name": "Ana García",
                    }
                )
                with patch(
                    "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient",
                    FakeClient,
                ), patch(
                    "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
                    return_value=SimpleNamespace(
                        invoke=lambda inputs: AppointmentDetails()
                    ),
                ):
                    final = await appointment_services_subgraph.ainvoke(result)
                if intent == "reschedule_appointment":
                    self.assertEqual(final["pending_question"], "appointment_details")
                    self.assertEqual(final["appointment_intent"], intent)
                elif intent == "cancel_appointment":
                    self.assertEqual(final["pending_question"], "cancel_confirmation")
                    self.assertEqual(final["appointment_intent"], intent)
                else:
                    self.assertIn("próxima cita", final["messages"][-1].content)
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
        message = HumanMessage(content=state.pop("message", "Solicitud de prueba"))
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

    def test_pending_details_preserve_intent_and_collected_values(self):
        starts_at = datetime(2026, 9, 10, 10, 0)
        for category in ("service_request", "confirmation"):
            with self.subTest(category=category):
                result = self.categorize(
                    category,
                    appointment_intent="book_appointment",
                    current_flow="appointment_services",
                    pending_question="appointment_details",
                    next_action="collect_appointment_details",
                    service_name="Corte de cabello",
                    starts_at=starts_at,
                )

                self.assertEqual(result["appointment_intent"], "book_appointment")
                self.assertEqual(result["current_flow"], "appointment_services")
                self.assertEqual(result["pending_question"], "appointment_details")
                self.assertEqual(result["next_action"], "collect_appointment_details")
                self.assertEqual(result["service_name"], "Corte de cabello")
                self.assertEqual(result["starts_at"], starts_at)

    def test_affirmative_booking_reply_is_confirmation_when_classifier_mislabels_it(self):
        result = self.categorize(
            "new_appointment",
            message="Sí, resérvala",
            appointment_intent="book_appointment",
            current_flow="appointment_services",
            pending_question="booking_confirmation",
            next_action="confirm_booking",
            service_id="service-1",
            business_staff_id="staff-1",
            starts_at=datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
            ends_at=datetime.fromisoformat("2026-09-10T11:00:00-06:00"),
        )

        self.assertEqual(result["message_category"], "confirmation")
        self.assertEqual(result["appointment_intent"], "book_appointment")
        self.assertEqual(result["pending_question"], "booking_confirmation")

    def test_explicit_booking_request_uses_the_available_slot_without_asking_again(self):
        from src.nodes.appointment_services.appointment_validation_node import (
            appointment_validation_node,
        )

        starts_at = datetime.fromisoformat("2026-09-21T09:00:00-06:00")
        ends_at = datetime.fromisoformat("2026-09-21T10:00:00-06:00")
        result = self.categorize(
            "new_appointment",
            message="Okay, podrías agendarme ese día y esa hora por favor?",
            appointment_intent="check_availability",
            current_flow="appointment_services",
            next_action="check_availability",
            service_id="service-1",
            business_staff_id="staff-1",
            service_name="Limpieza dental",
            starts_at=starts_at,
            ends_at=ends_at,
        )

        self.assertEqual(result["message_category"], "confirmation")
        self.assertEqual(result["appointment_intent"], "book_appointment")
        self.assertEqual(result["service_id"], "service-1")
        self.assertEqual(result["business_staff_id"], "staff-1")
        self.assertEqual(result["starts_at"], starts_at)
        self.assertEqual(result["ends_at"], ends_at)
        self.assertEqual(
            appointment_validation_node(result)["next_action"],
            "book_appointment",
        )


class AppointmentExplicitGraphTests(unittest.TestCase):
    def test_existing_appointment_intents_route_through_lookup(self):
        from src.nodes.appointment_services.appointment_validation_node import (
            appointment_validation_node,
        )

        for intent in ("reschedule_appointment", "cancel_appointment"):
            with self.subTest(intent=intent):
                result = appointment_validation_node(
                    {
                        "message_category": intent,
                        "appointment_intent": intent,
                        "current_flow": "appointment_services",
                    }
                )
                self.assertEqual(result["next_action"], "lookup_appointment")

    def test_confirmations_route_to_the_matching_mutation(self):
        from src.nodes.appointment_services.appointment_validation_node import (
            appointment_validation_node,
        )

        collect_reschedule_details = appointment_validation_node(
            {
                "message_category": "reschedule_appointment",
                "appointment_intent": "reschedule_appointment",
                "current_flow": "appointment_services",
                "active_appointment": {"id": "appointment-1"},
            }
        )
        cancel = appointment_validation_node(
            {
                "message_category": "confirmation",
                "appointment_intent": "cancel_appointment",
                "current_flow": "appointment_services",
                "active_appointment": {"id": "appointment-1"},
                "pending_question": "cancel_confirmation",
            }
        )
        reschedule = appointment_validation_node(
            {
                "message_category": "confirmation",
                "appointment_intent": "reschedule_appointment",
                "current_flow": "appointment_services",
                "active_appointment": {"id": "appointment-1"},
                "pending_question": "reschedule_confirmation",
                "service_id": "service-1",
                "business_staff_id": "staff-1",
                "starts_at": datetime.fromisoformat("2026-09-20T10:00:00-06:00"),
                "ends_at": datetime.fromisoformat("2026-09-20T11:00:00-06:00"),
            }
        )

        self.assertEqual(
            collect_reschedule_details["next_action"],
            "collect_appointment_details",
        )
        self.assertEqual(cancel["next_action"], "cancel_appointment")
        self.assertEqual(reschedule["next_action"], "reschedule_appointment")
        self.assertEqual(cancel["pending_question"], "cancel_confirmation")
        self.assertEqual(reschedule["pending_question"], "reschedule_confirmation")

    def test_subgraph_exposes_lookup_transition(self):
        from src.graph.appointment_services_subgraph import AppointmentServicesSubgraph

        graph = AppointmentServicesSubgraph().graph.get_graph()

        self.assertIn("lookup_appointment", graph.nodes)
        self.assertIn(
            ("appointment_validation", "lookup_appointment"),
            {(edge.source, edge.target) for edge in graph.edges},
        )

    def test_lookup_continues_only_reschedule_detail_collection(self):
        from src.graph.appointment_services_subgraph import (
            route_after_appointment_lookup,
        )

        self.assertEqual(
            route_after_appointment_lookup(
                {"next_action": "collect_appointment_details"}
            ),
            "collect_appointment_details",
        )
        self.assertEqual(
            route_after_appointment_lookup({"next_action": "cancel_appointment"}),
            "end",
        )

    def test_actions_are_terminal(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        graph = appointment_services_subgraph.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}
        self.assertNotIn("tools", graph.nodes)
        self.assertNotIn("appointment_agent", graph.nodes)
        self.assertIn("appointment_validation", graph.nodes)
        for action in APPOINTMENT_CASES.values():
            self.assertIn((action, "__end__"), edges)

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

    def test_complete_details_reach_availability_with_validated_state(self):
        from src.graph import appointment_services_subgraph as graph_module
        from src.models.appointment_details import AppointmentDetails

        local_timezone = timezone(timedelta(hours=-6))
        starts_at = datetime(2026, 9, 10, 10, 0, tzinfo=local_timezone)
        ends_at = datetime(2026, 9, 10, 11, 0, tzinfo=local_timezone)

        def reached_availability(state):
            self.assertEqual(state["service_name"], "Masaje")
            self.assertEqual(state["starts_at"], starts_at)
            return {
                "service_id": "availability-reached",
                "business_staff_id": "staff-1",
                "ends_at": ends_at,
                "messages": [AIMessage(content="Disponibilidad consultada")],
            }

        with patch.dict(
            graph_module.NODES,
            {"check_availability": reached_availability},
        ):
            graph = graph_module.AppointmentServicesSubgraph().graph

        base = {
            "messages": [HumanMessage(content="Quiero agendar")],
            "current_message": HumanMessage(content="Quiero agendar"),
            "message_category": "new_appointment",
            "business_id": str(uuid4()),
            "customer_id": "customer-1",
            "current_flow": "appointment_services",
        }
        agent = SimpleNamespace(
            invoke=lambda inputs: AppointmentDetails(
                service_name="Masaje", starts_at=starts_at
            )
        )
        with patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=agent,
        ):
            result = graph.invoke(base)

        self.assertEqual(result["service_id"], "availability-reached")
        self.assertEqual(result["service_name"], "Masaje")
        self.assertEqual(result["starts_at"], starts_at)
        self.assertEqual(result["ends_at"], ends_at)

    def test_missing_detail_is_preserved_and_followup_reaches_availability_once(self):
        from src.graph import appointment_services_subgraph as graph_module
        from src.models.appointment_details import AppointmentDetails

        local_timezone = timezone(timedelta(hours=-6))
        starts_at = datetime(2026, 9, 10, 10, 0, tzinfo=local_timezone)
        ends_at = datetime(2026, 9, 10, 11, 0, tzinfo=local_timezone)
        availability_inputs = []

        def reached_availability(state):
            availability_inputs.append(
                (state.get("service_name"), state.get("starts_at"))
            )
            return {
                "service_id": "availability-reached",
                "business_staff_id": "staff-1",
                "ends_at": ends_at,
                "messages": [AIMessage(content="Disponibilidad consultada")],
            }

        with patch.dict(
            graph_module.NODES,
            {"check_availability": reached_availability},
        ):
            graph = graph_module.AppointmentServicesSubgraph().graph

        first_message = HumanMessage(content="Quiero un masaje")
        base = {
            "messages": [first_message],
            "current_message": first_message,
            "message_category": "new_appointment",
            "business_id": str(uuid4()),
            "customer_id": "customer-1",
            "current_flow": "appointment_services",
        }
        agent = SimpleNamespace(
            invoke=lambda inputs: AppointmentDetails(service_name="Masaje")
        )
        with patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=agent,
        ):
            incomplete = graph.invoke(base)

        self.assertEqual(incomplete["pending_question"], "appointment_details")
        self.assertEqual(incomplete["next_action"], "collect_appointment_details")
        self.assertEqual(incomplete["service_name"], "Masaje")
        self.assertIn("fecha y hora", incomplete["messages"][-1].content.lower())
        self.assertIsNone(incomplete.get("service_id"))
        self.assertEqual(availability_inputs, [])

        followup = HumanMessage(content="Mañana a las 10")
        agent = SimpleNamespace(
            invoke=lambda inputs: AppointmentDetails(starts_at=starts_at)
        )
        with patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=agent,
        ):
            complete = graph.invoke(
                {
                    **incomplete,
                    "messages": [*incomplete["messages"], followup],
                    "current_message": followup,
                    "message_category": "confirmation",
                }
            )

        self.assertEqual(availability_inputs, [("Masaje", starts_at)])
        self.assertEqual(complete["service_id"], "availability-reached")
        self.assertEqual(complete["service_name"], "Masaje")
        self.assertEqual(complete["starts_at"], starts_at)
        self.assertEqual(complete["ends_at"], ends_at)
        self.assertEqual(complete["next_action"], "check_availability")

    def test_availability_confirmation_books_exactly_once(self):
        from src.graph import appointment_services_subgraph as graph_module
        from src.models.appointment_details import AppointmentDetails

        starts_at = datetime.fromisoformat("2026-09-10T10:00:00-06:00")
        ends_at = datetime.fromisoformat("2026-09-10T11:00:00-06:00")
        availability_calls = []
        booking_calls = []

        def check_availability(state):
            availability_calls.append(state)
            return {
                "service_id": "service-1",
                "business_staff_id": "staff-1",
                "ends_at": ends_at,
                "pending_question": "booking_confirmation",
                "next_action": "confirm_booking",
                "messages": [AIMessage(content="El horario está disponible")],
            }

        def book_appointment(state):
            booking_calls.append(state)
            return {
                **clear_appointment_state(),
                "messages": [AIMessage(content="Tu cita quedó agendada")],
            }

        with patch.dict(
            graph_module.NODES,
            {
                "check_availability": check_availability,
                "book_appointment": book_appointment,
            },
        ):
            graph = graph_module.AppointmentServicesSubgraph().graph

        incoming = HumanMessage(content="Quiero un masaje mañana a las 10")
        agent = SimpleNamespace(
            invoke=lambda inputs: AppointmentDetails(
                service_name="Masaje", starts_at=starts_at
            )
        )
        with patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=agent,
        ):
            available = graph.invoke(
                {
                    "messages": [incoming],
                    "current_message": incoming,
                    "message_category": "new_appointment",
                    "business_id": str(uuid4()),
                    "customer_id": str(uuid4()),
                    "current_flow": "appointment_services",
                }
            )

        self.assertEqual(available["appointment_intent"], "book_appointment")
        self.assertEqual(available["next_action"], "confirm_booking")
        self.assertEqual(available["pending_question"], "booking_confirmation")
        confirmation = HumanMessage(content="Sí, reserva ese horario")
        with patch(
            "src.nodes.message_categorizer_node.message_categorizer_agent"
        ) as categorizer:
            categorizer.return_value.invoke.return_value = SimpleNamespace(
                category=SimpleNamespace(value="new_appointment")
            )
            categorized = message_categorizer_node(
                {
                    **available,
                    "messages": [*available["messages"], confirmation],
                    "current_message": confirmation,
                }
            )
        booked = graph.invoke(categorized)

        self.assertEqual(len(availability_calls), 1)
        self.assertEqual(len(booking_calls), 1)
        self.assertEqual(booking_calls[0]["service_id"], "service-1")
        self.assertEqual(booking_calls[0]["business_staff_id"], "staff-1")
        self.assertEqual(booking_calls[0]["starts_at"], starts_at)
        self.assertEqual(booking_calls[0]["ends_at"], ends_at)
        self.assertIn("agendada", booked["messages"][-1].content)

    def test_confirmation_for_check_only_intent_does_not_book(self):
        from src.nodes.appointment_services.appointment_validation_node import (
            appointment_validation_node,
        )

        result = appointment_validation_node(
            {
                "message_category": "confirmation",
                "appointment_intent": "check_availability",
                "current_flow": "appointment_services",
                "service_id": "service-1",
                "business_staff_id": "staff-1",
                "starts_at": datetime.fromisoformat("2026-09-10T10:00:00-06:00"),
                "ends_at": datetime.fromisoformat("2026-09-10T11:00:00-06:00"),
            }
        )

        self.assertEqual(result["next_action"], "collect_appointment_details")


class AppointmentExpandedRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_reschedule_lookup_availability_and_confirmation_flow(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        from src.models.appointment_details import AppointmentDetails

        existing = JsonResponse(
            {
                "appointment_id": "appointment-1",
                "starts_at": "2026-09-18T10:00:00-06:00",
                "service_name": "Corte de cabello",
                "staff_name": "Ana García",
            }
        )
        available = JsonResponse(
            {
                "available": True,
                "service_id": "service-1",
                "business_staff_id": "staff-1",
                "ends_at": "2026-09-20T11:00:00-06:00",
            }
        )
        updated = JsonResponse({"id": "appointment-1"})
        client = FakeClient()
        responses = iter((existing, available))

        async def get(url, **kwargs):
            return next(responses)

        client.get = get
        client.put = unittest.mock.AsyncMock(return_value=updated)
        client_context = unittest.mock.MagicMock()
        client_context.return_value.__aenter__ = unittest.mock.AsyncMock(
            return_value=client
        )
        client_context.return_value.__aexit__ = unittest.mock.AsyncMock(
            return_value=False
        )
        starts_at = datetime.fromisoformat("2026-09-20T10:00:00-06:00")
        incoming = HumanMessage(content="Mueve mi cita al 20 de septiembre a las 10")

        with patch(
            "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient",
            client_context,
        ), patch(
            "src.nodes.appointment_services.appointment_action_nodes.API_URL",
            "https://api.example.test",
        ), patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=SimpleNamespace(
                invoke=lambda inputs: AppointmentDetails(starts_at=starts_at)
            ),
        ):
            pending = await appointment_services_subgraph.ainvoke(
                {
                    "messages": [incoming],
                    "current_message": incoming,
                    "message_category": "reschedule_appointment",
                    "business_id": "business-1",
                    "customer_id": "customer-1",
                    "current_flow": "appointment_services",
                }
            )
            confirmation = HumanMessage(content="Sí, reprograma la cita")
            result = await appointment_services_subgraph.ainvoke(
                {
                    **pending,
                    "messages": [*pending["messages"], confirmation],
                    "current_message": confirmation,
                    "message_category": "confirmation",
                }
            )

        self.assertEqual(pending["pending_question"], "reschedule_confirmation")
        self.assertEqual(pending["active_appointment"]["id"], "appointment-1")
        self.assertIn("reprogramada", result["messages"][-1].content)
        self.assertIsNone(result["active_appointment"])
        client.put.assert_awaited_once_with(
            "https://api.example.test/appointments/reschedule",
            params={
                "business_id": "business-1",
                "appointment_id": "appointment-1",
            },
            json={
                "starts_at": "2026-09-20T10:00:00-06:00",
                "ends_at": "2026-09-20T11:00:00-06:00",
            },
        )

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

    async def test_cancel_confirmation_reaches_writer_unchanged(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph
        FakeClient.response = JsonResponse(
            {
                "appointment_id": "appointment-1",
                "starts_at": "2026-09-18T10:00:00-06:00",
                "service_name": "Corte de cabello",
                "staff_name": "Ana García",
            }
        )
        with patch(
            "src.nodes.appointment_services.appointment_action_nodes.httpx.AsyncClient",
            FakeClient,
        ):
            result = await appointment_services_subgraph.ainvoke({
                "messages": [HumanMessage(content="Cancela mi cita")],
                "message_category": "cancel_appointment",
                "business_id": str(uuid4()), "customer_id": "customer-1",
            })
        with patch("src.nodes.message_writer_node.message_writer") as model:
            written = message_writer_node(result)
        model.assert_not_called()
        self.assertIn("cancelar", written["message_response"].lower())
        self.assertEqual(result["pending_question"], "cancel_confirmation")
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
    async def test_reschedule_tool_uses_put_contract(self):
        start = datetime.fromisoformat("2026-08-29T11:00:00-06:00")
        response = unittest.mock.Mock()
        response.json.return_value = {"id": "appointment-1"}
        client = unittest.mock.AsyncMock()
        client.put.return_value = response
        client_class = unittest.mock.MagicMock()
        client_class.return_value.__aenter__ = unittest.mock.AsyncMock(
            return_value=client
        )
        client_class.return_value.__aexit__ = unittest.mock.AsyncMock(
            return_value=False
        )
        state = {
            "business_id": "business-1",
            "active_appointment": {"id": "appointment-1"},
            "confirmed_slot": {"starts_at": start.isoformat()},
        }

        with patch(
            "src.nodes.tools.services.services_tools.httpx.AsyncClient",
            client_class,
        ), patch(
            "src.nodes.tools.services.services_tools.API_URL",
            "https://api.example.test",
        ):
            await reschedule_appointment.coroutine(
                AppointmentInput(
                    starts_at=start,
                    ends_at=start + timedelta(hours=1),
                ),
                "tool-reschedule",
                state,
            )

        client.put.assert_awaited_once_with(
            "https://api.example.test/appointments/reschedule",
            params={
                "business_id": "business-1",
                "appointment_id": "appointment-1",
            },
            json={
                "starts_at": "2026-08-29T11:00:00-06:00",
                "ends_at": "2026-08-29T12:00:00-06:00",
            },
        )

    async def test_create_callers_return_error_when_required_ids_are_missing(self):
        start = datetime.fromisoformat("2026-08-28T10:00:00")
        appointment = AppointmentInput(
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        state = {
            "business_id": uuid4(),
            "customer_id": str(uuid4()),
            "customer": {"id": str(uuid4())},
            "confirmed_slot": {"starts_at": start.isoformat()},
        }

        services_result = await create_appointment.coroutine(
            appointment,
            "tool-create",
            state,
        )
        messages_result = await create_message_appointment.coroutine(
            appointment,
            state,
        )

        for result in (services_result, messages_result):
            self.assertIsInstance(result, str)
            self.assertIn("error creating appointment", result)

    async def test_create_completion_clears_flow(self):
        start = datetime.fromisoformat("2026-08-28T10:00:00")
        FakeClient.response = JsonResponse({"id": str(uuid4())})
        state = {
            "business_id": uuid4(),
            "customer_id": str(uuid4()),
            "service_id": uuid4(),
            "business_staff_id": uuid4(),
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
