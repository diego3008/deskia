from langchain_core.messages import SystemMessage


LANGUAGE_DIRECTIVE = SystemMessage(
    content="Always respond to the user in Spanish, regardless of the language used above."
)
