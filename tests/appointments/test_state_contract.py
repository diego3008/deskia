from datetime import datetime, timezone
from uuid import uuid4

from src.nodes.appointments.context import to_appointment_input
from src.structured_outputs import (
    AppointmentOperation,
    AppointmentPhase,
    ConfirmationStatus,
)


def test_projection_preserves_typed_appointment_details():
    appointment_id = uuid4()
    service_id = uuid4()
    starts_at = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    ends_at = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
    parent = {
        "business_id": uuid4(),
        "business_timezone": "America/Monterrey",
        "customer_id": uuid4(),
        "current_message": "Move it to Friday at 9",
        "messages": [],
        "appointment": {
            "operation": AppointmentOperation.RESCHEDULE,
            "phase": AppointmentPhase.CHECKING_AVAILABILITY,
            "service_id": service_id,
            "requested_start": starts_at,
            "requested_end": ends_at,
            "selected_appointment": {"id": appointment_id},
            "availability_evidence": {
                "starts_at": starts_at,
                "ends_at": ends_at,
                "service_id": service_id,
                "available": True,
            },
            "confirmation_status": ConfirmationStatus.NOT_REQUESTED,
            "result": None,
            "error": None,
        },
    }

    child = to_appointment_input(parent)

    assert child["operation"] == AppointmentOperation.RESCHEDULE
    assert child["phase"] == AppointmentPhase.CHECKING_AVAILABILITY
    assert child["service_id"] == service_id
    assert child["requested_start"] == starts_at
    assert child["requested_end"] == ends_at
    assert child["selected_appointment"] == {"id": appointment_id}
    assert child["availability_evidence"]["available"] is True
    assert child["confirmation_status"] == ConfirmationStatus.NOT_REQUESTED
