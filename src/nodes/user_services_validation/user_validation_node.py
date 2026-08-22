


from src.state import UserValidationState


def user_validations_node(state: UserValidationState) -> dict:
    pending_question = state.get("pending_question")

    if pending_question == "is_new_client" and state.get("message_category") == "decline":
        return {
            "pending_question": "existing_customer_email",
            "next_action": "request_existing_customer_email",
        }

    if pending_question == "existing_customer_email":
        email = state.get("user_data", {}).get("email")
        if email:
            return {
                "pending_question": None,
                "next_action": "lookup_customer",
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
        if state.get("user_data", {}).get("email"):
            return {
                "pending_question": None,
                "next_action": "create_customer",
            }

        return {
            "pending_question": "new_customer_details",
            "next_action": "request_new_customer_details",
        }

    return {}
