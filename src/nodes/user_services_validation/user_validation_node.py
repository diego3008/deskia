
import re

from langchain_core.messages import HumanMessage

from src.helpers.workflow import CUSTOMER_QUESTION_ACTIONS
from src.state import UserValidationState
from src.structured_outputs import APPOINTMENT_CATEGORIES


EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])")


def _latest_human_text(state: UserValidationState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return message.content.strip()
    return ""


def user_validations_node(state: UserValidationState) -> dict:
    pending_question = state.get("pending_question")
    user_data = state.get("user_data", {})

    if state.get("next_action") == "retry_customer_lookup":
        return {"next_action": "lookup_customer"}

    if state.get("next_action") == "retry_customer_creation":
        return {"next_action": "create_customer"}

    if state.get("message_category") in APPOINTMENT_CATEGORIES and (
        not pending_question or pending_question in CUSTOMER_QUESTION_ACTIONS
    ):
        question = pending_question or "existing_customer_email"
        return {
            "pending_question": question,
            "next_action": CUSTOMER_QUESTION_ACTIONS[question],
            **({} if pending_question else {"user_data": {}}),
        }

    if pending_question == "existing_customer_email":
        emails = EMAIL_PATTERN.findall(_latest_human_text(state))
        if emails:
            return {
                "pending_question": None,
                "next_action": "lookup_customer",
                "user_data": {"email": emails[-1]},
            }

        return {
            "pending_question": "existing_customer_email",
            "next_action": "request_existing_customer_email",
        }

    if pending_question == "confirm_create_customer":
        if state.get("message_category") == "confirmation":
            return {
                "pending_question": "new_customer_details",
                "next_action": "request_new_customer_details",
            }

        return {
            "pending_question": None,
            "next_action": "clarify_intent",
        }

    if pending_question == "new_customer_details":
        name = re.sub(
            r"^(?:my name is|mi nombre es)\s+", "", _latest_human_text(state), flags=re.I
        )
        name_parts = name.split(maxsplit=1)
        # ponytail: compound first names remain ambiguous; use structured extraction if that distinction matters.
        if user_data.get("email") and len(name_parts) == 2:
            return {
                "pending_question": None,
                "next_action": "create_customer",
                "user_data": {
                    **user_data,
                    "first_name": name_parts[0],
                    "last_name": name_parts[1],
                },
            }

        return {
            "pending_question": "new_customer_details",
            "next_action": "request_new_customer_details",
        }

    return {}
