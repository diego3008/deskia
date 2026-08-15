from langchain_anthropic import ChatAnthropic
# from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_openrouter import ChatOpenRouter

from src.prompts import MESSAGE_WRITER_PROMPT
from src.state import OutBoundsMessge


def message_writer():
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    llm = ChatOpenRouter(model="google/gemini-3.5-flash-lite", temperature=0)

    prompt = PromptTemplate(
        template=MESSAGE_WRITER_PROMPT,
        input_variables=["message_category", "message_content", "is_first_message", "language"],
    )

    return prompt | llm.with_structured_output(OutBoundsMessge)
