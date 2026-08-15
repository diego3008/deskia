


from enum import Enum

class AppointmentStatusCode(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"