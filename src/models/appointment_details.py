from datetime import datetime

from pydantic import BaseModel


class AppointmentDetails(BaseModel):
    service_name: str | None = None
    starts_at: datetime | None = None
