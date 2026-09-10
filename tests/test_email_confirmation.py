import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from googleapiclient.errors import HttpError
from pydantic import ValidationError


SUCCESS = {
    "status": "succeeded",
    "operation": "booked",
    "operation_id": "mutation-1",
    "appointment_id": "appointment-1",
    "business_id": "business-1",
    "customer_id": "customer-1",
    "recipient_email": "ana@example.com",
    "starts_at": "2026-09-10T10:00:00-06:00",
}


class OutcomeTests(unittest.TestCase):
    def test_only_confirmed_mutations_with_usable_dates_are_valid(self):
        from src.models.appointments import AppointmentOutcome

        for operation in ("booked", "rescheduled", "cancelled"):
            self.assertEqual(
                AppointmentOutcome.model_validate(
                    {**SUCCESS, "operation": operation}
                ).operation,
                operation,
            )
        for change in (
            {"status": "failed"},
            {"operation": "check_availability"},
            {"operation_id": ""},
            {"starts_at": None},
            {"starts_at": "2026-09-10T10:00:00"},
            {"ends_at": "2026-09-10T09:00:00-06:00"},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                AppointmentOutcome.model_validate({**SUCCESS, **change})
        cancelled = AppointmentOutcome.model_validate(
            {**SUCCESS, "operation": "cancelled", "starts_at": None}
        )
        self.assertEqual(cancelled.appointment_id, "appointment-1")


class NotificationStateTests(unittest.IsolatedAsyncioTestCase):
    def test_listener_clears_transient_email_state_and_preserves_receipts(self):
        from src.nodes.message_listener_node import message_listener_node

        receipt = {"mutation-1": {"status": "sent"}}
        for content in ("Hola", "  "):
            with self.subTest(content=content):
                state = {
                    "messages": [HumanMessage(content=content)],
                    "appointment_outcome": SUCCESS,
                    "email_draft": {"to": "ana@example.com"},
                    "email_confirmation": {"status": "sent"},
                    "email_receipts": receipt,
                }

                merged = {**state, **message_listener_node(state)}

                self.assertIsNone(merged["appointment_outcome"])
                self.assertIsNone(merged["email_draft"])
                self.assertIsNone(merged["email_confirmation"])
                self.assertEqual(merged["email_receipts"], receipt)

    async def test_incomplete_booking_preserves_a_stale_appointment_outcome(self):
        from src.nodes.appointment_services.appointment_action_nodes import (
            book_appointment_node,
        )

        state = {"appointment_outcome": SUCCESS}
        result = await book_appointment_node(state)
        merged = {**state, **result}

        self.assertEqual(merged["appointment_outcome"], SUCCESS)
        self.assertNotIn("appointment_outcome", result)


class EmailCompositionTests(unittest.TestCase):
    def test_uses_literal_subjects_and_all_available_appointment_details(self):
        from src.nodes.email_confirmation_nodes import write_email_node

        cases = (
            ("booked", "Confirmación de cita"),
            ("rescheduled", "Cita reprogramada"),
            ("cancelled", "Cita cancelada"),
        )
        for operation, subject in cases:
            outcome = {
                **SUCCESS,
                "operation": operation,
                "ends_at": "2026-09-10T11:00:00-06:00",
                "previous_starts_at": "2026-09-09T10:00:00-06:00",
            }
            with self.subTest(operation=operation):
                draft = write_email_node(
                    {
                        "business_id": "business-1",
                        "customer_id": "customer-1",
                        "appointment_outcome": outcome,
                    }
                )["email_draft"]
                self.assertEqual(draft["subject"], subject)
                self.assertEqual(draft["to"], "ana@example.com")
                self.assertIn("Referencia: appointment-1", draft["body"])
                self.assertIn("Fecha y hora: 2026-09-10 10:00 -0600", draft["body"])
                self.assertIn("Fin: 2026-09-10 11:00 -0600", draft["body"])
                self.assertIn("Horario anterior: 2026-09-09 10:00 -0600", draft["body"])

    def test_cancelled_event_without_dates_is_composed(self):
        from src.nodes.email_confirmation_nodes import write_email_node

        result = write_email_node(
            {
                "business_id": "business-1",
                "customer_id": "customer-1",
                "appointment_outcome": {
                    **SUCCESS,
                    "operation": "cancelled",
                    "starts_at": None,
                },
            }
        )

        self.assertEqual(result["email_draft"]["body"], "Tu cita ha sido cancelada.\nReferencia: appointment-1")

    def test_rejects_missing_mismatched_or_malformed_current_identity(self):
        from src.nodes.email_confirmation_nodes import write_email_node

        states = (
            {"business_id": "other", "customer_id": "customer-1"},
            {"business_id": "business-1", "customer_id": "other"},
            {"business_id": "business-1", "customer": "malformed"},
            {},
        )
        for identity in states:
            with self.subTest(identity=identity):
                result = write_email_node({**identity, "appointment_outcome": SUCCESS})
                self.assertIsNone(result["email_draft"])
                self.assertIsNone(result["email_confirmation"])


class EmailGraphTests(unittest.IsolatedAsyncioTestCase):
    def state(self, **outcome_changes):
        return {
            "business_id": "business-1",
            "customer_id": "customer-1",
            "appointment_outcome": {**SUCCESS, **outcome_changes},
            "message_response": "Tu cita está confirmada.",
        }

    async def test_sends_once_per_saved_operation_and_preserves_chat(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph

        state = self.state()
        with patch("src.nodes.email_confirmation_nodes.send_email", return_value="gmail-1") as send:
            first = await email_confirmation_graph.ainvoke(state)
            again = await email_confirmation_graph.ainvoke(first)

        self.assertEqual(send.call_count, 1)
        self.assertEqual(again["email_confirmation"]["status"], "sent")
        self.assertEqual(again["email_confirmation"]["gmail_message_id"], "gmail-1")
        self.assertEqual(again["message_response"], state["message_response"])
        self.assertEqual(again["appointment_outcome"], SUCCESS)

    async def test_different_reschedule_operation_ids_each_send_once(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph

        with patch("src.nodes.email_confirmation_nodes.send_email", side_effect=("gmail-1", "gmail-2")) as send:
            first = await email_confirmation_graph.ainvoke(
                self.state(operation="rescheduled", operation_id="reschedule-1")
            )
            second = await email_confirmation_graph.ainvoke(
                {
                    **first,
                    "appointment_outcome": {
                        **SUCCESS,
                        "operation": "rescheduled",
                        "operation_id": "reschedule-2",
                    },
                }
            )
            replayed = await email_confirmation_graph.ainvoke(second)

        self.assertEqual(send.call_count, 2)
        self.assertEqual(replayed["email_confirmation"]["gmail_message_id"], "gmail-2")
        self.assertEqual(set(replayed["email_receipts"]), {"reschedule-1", "reschedule-2"})

    async def test_missing_recipient_is_recorded_as_skipped(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph

        with patch("src.nodes.email_confirmation_nodes.send_email") as send:
            result = await email_confirmation_graph.ainvoke(self.state(recipient_email="  "))

        send.assert_not_called()
        self.assertEqual(
            result["email_confirmation"],
            {"operation_id": "mutation-1", "status": "skipped", "reason": "recipient_missing"},
        )

    async def test_configuration_and_content_errors_are_failed(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph
        from src.utils.gmail_utils import GmailConfigurationError

        for error in (GmailConfigurationError("bad config"), ValueError("bad content")):
            with self.subTest(error=type(error).__name__), patch(
                "src.nodes.email_confirmation_nodes.send_email", side_effect=error
            ):
                result = await email_confirmation_graph.ainvoke(self.state())
                self.assertEqual(result["email_confirmation"]["status"], "failed")

    async def test_http_rejection_is_failed_but_uncertain_delivery_is_unknown(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph

        cases = ((400, "failed"), (408, "unknown"), (500, "unknown"))
        for status, expected in cases:
            response = Mock(status=status, reason="error")
            error = HttpError(response, b'{"error": {"message": "no"}}')
            with self.subTest(status=status), patch(
                "src.nodes.email_confirmation_nodes.send_email", side_effect=error
            ):
                result = await email_confirmation_graph.ainvoke(self.state())
                self.assertEqual(result["email_confirmation"]["status"], expected)

        with patch("src.nodes.email_confirmation_nodes.send_email", side_effect=TimeoutError):
            result = await email_confirmation_graph.ainvoke(self.state())
        self.assertEqual(result["email_confirmation"]["status"], "unknown")
        self.assertEqual(result["message_response"], "Tu cita está confirmada.")
        self.assertEqual(result["appointment_outcome"], SUCCESS)

    async def test_saved_receipts_suppress_replay_even_when_empty(self):
        from src.graph.email_confirmation_subgraph import email_confirmation_graph

        for receipt in (
            {"operation_id": "mutation-1", "status": "sent"},
            {"operation_id": "mutation-1", "status": "skipped"},
            {"operation_id": "mutation-1", "status": "failed"},
            {"operation_id": "mutation-1", "status": "unknown"},
            {},
        ):
            with self.subTest(receipt=receipt), patch("src.nodes.email_confirmation_nodes.send_email") as send:
                result = await email_confirmation_graph.ainvoke(
                    {**self.state(), "email_receipts": {"mutation-1": receipt}}
                )
                send.assert_not_called()
                self.assertEqual(result["email_confirmation"], receipt)


class EmailParentRoutingTests(unittest.TestCase):
    def test_only_fresh_confirmed_mutations_enter_email(self):
        from src.graph.appointment_booking_graph import route_after_message_writer

        state = {
            "business_id": "business-1",
            "customer_id": "customer-1",
            "appointment_outcome": SUCCESS,
        }
        for operation in ("booked", "rescheduled", "cancelled"):
            with self.subTest(operation=operation):
                self.assertEqual(
                    route_after_message_writer(
                        {
                            **state,
                            "appointment_outcome": {
                                **SUCCESS,
                                "operation": operation,
                                "starts_at": None if operation == "cancelled" else SUCCESS["starts_at"],
                            },
                        }
                    ),
                    "email_confirmation",
                )

        ineligible = (
            {"message_category": "new_appointment"},
            {**state, "appointment_outcome": None},
            {**state, "appointment_outcome": {**SUCCESS, "status": "failed"}},
            {**state, "appointment_outcome": {**SUCCESS, "operation": "check_availability"}},
            {**state, "business_id": "other"},
            {**state, "customer_id": "other"},
            {
                **state,
                "email_receipts": {
                    "mutation-1": {"operation_id": "mutation-1", "status": "sent"}
                },
            },
        )
        for invalid_state in ineligible:
            with self.subTest(state=invalid_state):
                self.assertEqual(route_after_message_writer(invalid_state), "end")


class EmailParentGraphTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def producer(outcome):
        from src.state import MessageGraphState

        graph = StateGraph(MessageGraphState)
        graph.add_node(
            "confirmed_operation",
            lambda state: {
                "appointment_outcome": outcome,
                "messages": [AIMessage(content="Tu cita quedó actualizada.")],
            },
        )
        graph.add_edge(START, "confirmed_operation")
        graph.add_edge("confirmed_operation", END)
        return graph.compile()

    @staticmethod
    def categorizer(category):
        return Mock(
            invoke=Mock(return_value=Mock(category=Mock(value=category)))
        )

    async def invoke_parent(self, appointment_graph, category, send_error=None, **state):
        from src.graph import appointment_booking_graph as parent

        incoming = HumanMessage(content="Actualiza mi cita")
        with (
            patch.object(parent, "appointment_services_subgraph", appointment_graph),
            patch(
                "src.nodes.message_categorizer_node.message_categorizer_agent",
                return_value=self.categorizer(category),
            ),
            patch(
                "src.nodes.email_confirmation_nodes.send_email",
                return_value="gmail-1",
                side_effect=send_error,
            ) as send,
        ):
            result = await parent.AppointmentBooking().graph.ainvoke(
                {
                    "messages": [incoming],
                    "business_id": "business-1",
                    "customer_id": "customer-1",
                    **state,
                }
            )
        return result, send

    async def test_confirmed_mutations_preserve_chat_and_record_sent(self):
        cases = (
            ("booked", "new_appointment"),
            ("rescheduled", "reschedule_appointment"),
            ("cancelled", "cancel_appointment"),
        )
        for operation, category in cases:
            outcome = {
                **SUCCESS,
                "operation": operation,
                "starts_at": None if operation == "cancelled" else SUCCESS["starts_at"],
            }
            with self.subTest(operation=operation):
                result, send = await self.invoke_parent(self.producer(outcome), category)
                self.assertEqual(result["message_response"], "Tu cita quedó actualizada.")
                self.assertEqual(result["messages"][0].content, "Actualiza mi cita")
                self.assertEqual(result["messages"][-1].content, "Tu cita quedó actualizada.")
                self.assertEqual(result["appointment_outcome"], outcome)
                self.assertEqual(result["email_confirmation"]["status"], "sent")
                self.assertEqual(result["email_receipts"]["mutation-1"]["status"], "sent")
                self.assertEqual(send.call_count, 1)

    async def test_pending_operations_do_not_send_even_with_stale_incoming_success(self):
        from src.graph.appointment_services_subgraph import appointment_services_subgraph

        for category in (
            "new_appointment",
            "check_availability",
            "reschedule_appointment",
            "cancel_appointment",
            "view_appointment",
        ):
            with self.subTest(category=category):
                result, send = await self.invoke_parent(
                    appointment_services_subgraph,
                    category,
                    appointment_outcome=SUCCESS,
                )
                send.assert_not_called()
                self.assertIsNone(result["appointment_outcome"])
                self.assertIsNone(result.get("email_confirmation"))

    async def test_email_failure_preserves_success_and_chat(self):
        outcome = {**SUCCESS, "operation": "rescheduled"}
        result, send = await self.invoke_parent(
            self.producer(outcome),
            "reschedule_appointment",
            send_error=ValueError("bad content"),
        )

        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["message_response"], "Tu cita quedó actualizada.")
        self.assertEqual(result["messages"][0].content, "Actualiza mi cita")
        self.assertEqual(result["messages"][-1].content, "Tu cita quedó actualizada.")
        self.assertEqual(result["appointment_outcome"], outcome)
        self.assertEqual(result["email_confirmation"]["status"], "failed")
