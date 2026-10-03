from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from src.prompts import MESSAGE_WRITER_PROMPT
from src.state import OutBoundsMessge


def message_writer():
    llm = ChatOpenAI(model="gpt-6-luna")

    prompt = PromptTemplate(
        template=MESSAGE_WRITER_PROMPT,
        input_variables=[
            "message_category",
            "message_content",
            "is_first_message",
            "conversation_history",
            "workflow_context",
            "retrieved_services"
        ],
    )

    return prompt | llm.with_structured_output(OutBoundsMessge)
