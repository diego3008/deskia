from langchain_anthropic import ChatAnthropic
from langchain.prompts import PromptTemplate
from src.prompts.agents import MESSAGE_CATEGORIZER_PROMPT
from src.state import OutBoundsMessge


def message_writer():
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    
    message_writer_prompt = PromptTemplate(
        template=MESSAGE_CATEGORIZER_PROMPT,
        input_variables=["message_category", "message_content", "context"]
    )

    message_writer_chain = message_writer_prompt | llm.with_structured_output(OutBoundsMessge)
    return message_writer_chain

