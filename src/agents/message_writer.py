from langchain_anthropic import ChatAnthropic
from langchain.prompts import PromptTemplate

from src.prompts import MESSAGE_WRITER_PROMPT
from src.state import OutBoundsMessge


def message_writer():
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

    prompt = PromptTemplate(
        template=MESSAGE_WRITER_PROMPT,
        input_variables=["message_category", "message_content", "is_first_message"],
    )

    return prompt | llm.with_structured_output(OutBoundsMessge)
