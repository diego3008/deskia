from langchain_core.prompts import PromptTemplate
from langchain_openrouter import ChatOpenRouter
from src.prompts import MESSAGE_WRITER_PROMPT
from src.state import OutBoundsMessge


def message_writer():
    llm = ChatOpenRouter(model="google/gemini-3.7-flash", temperature=0)

    prompt = PromptTemplate(
        template=MESSAGE_WRITER_PROMPT,
        input_variables=["message_category", "message_content", "is_first_message"],
    )

    return prompt | llm.with_structured_output(OutBoundsMessge)
