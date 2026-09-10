import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from src.models.appointment_details import AppointmentDetails
from src.nodes.appointment_services.appointment_details_node import (
    appointment_details_node,
)


class AppointmentDetailsNodeTests(unittest.TestCase):
    def extract(self, details, **state):
        agent = SimpleNamespace(invoke=lambda inputs: details)
        incoming = HumanMessage(content=state.pop("message", "Quiero una cita"))
        with patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=agent,
        ):
            return appointment_details_node(
                {
                    **state,
                    "current_message": incoming,
                    "messages": [incoming],
                }
            )

    def test_complete_details_route_to_availability(self):
        starts_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)

        result = self.extract(
            AppointmentDetails(service_name="Corte de cabello", starts_at=starts_at),
            ends_at=datetime(2026, 9, 10, 11, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["service_name"], "Corte de cabello")
        self.assertEqual(result["starts_at"], starts_at)
        self.assertEqual(result["next_action"], "check_availability")
        self.assertIsNone(result["pending_question"])
        self.assertNotIn("ends_at", result)
        self.assertNotIn("messages", result)

    def test_missing_time_asks_for_date_and_time(self):
        result = self.extract(AppointmentDetails(service_name="Masaje"))

        self.assertEqual(result["service_name"], "Masaje")
        self.assertIsNone(result["starts_at"])
        self.assertEqual(result["pending_question"], "appointment_details")
        self.assertEqual(result["next_action"], "collect_appointment_details")
        self.assertIsInstance(result["messages"][0], AIMessage)
        self.assertIn("fecha y hora", result["messages"][0].content.lower())

    def test_missing_service_asks_which_service(self):
        starts_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)

        result = self.extract(AppointmentDetails(starts_at=starts_at))

        self.assertIsNone(result["service_name"])
        self.assertEqual(result["starts_at"], starts_at)
        self.assertEqual(result["pending_question"], "appointment_details")
        self.assertEqual(result["next_action"], "collect_appointment_details")
        self.assertIsInstance(result["messages"][0], AIMessage)
        self.assertIn("servicio", result["messages"][0].content.lower())

    def test_followup_preserves_existing_start_when_service_arrives(self):
        starts_at = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)

        result = self.extract(
            AppointmentDetails(service_name="Corte de cabello"),
            message="Corte de cabello",
            starts_at=starts_at,
            service_name=None,
        )

        self.assertEqual(result["service_name"], "Corte de cabello")
        self.assertEqual(result["starts_at"], starts_at)
        self.assertEqual(result["next_action"], "check_availability")

    def test_reschedule_preserves_the_existing_appointment_service(self):
        starts_at = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)

        result = self.extract(
            AppointmentDetails(service_name="Tinte", starts_at=starts_at),
            appointment_intent="reschedule_appointment",
            service_name="Corte de cabello",
        )

        self.assertEqual(result["service_name"], "Corte de cabello")
        self.assertEqual(result["starts_at"], starts_at)

    def test_naive_extracted_start_uses_supplied_local_timezone(self):
        captured = {}

        def invoke(inputs):
            captured.update(inputs)
            return AppointmentDetails(
                service_name="Masaje",
                starts_at=datetime(2026, 9, 10, 10, 0),
            )

        incoming = HumanMessage(content="Masaje mañana a las 10")
        with patch(
            "src.nodes.appointment_services.appointment_details_node.appointment_details_agent",
            return_value=SimpleNamespace(invoke=invoke),
        ):
            result = appointment_details_node(
                {"current_message": incoming, "messages": [incoming]}
            )

        self.assertIsNotNone(result["starts_at"].utcoffset())
        self.assertEqual(str(result["starts_at"].tzinfo), captured["timezone"])
        self.assertNotIn("ends_at", result)


if __name__ == "__main__":
    unittest.main()
