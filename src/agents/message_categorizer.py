from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv

from src.structured_outputs import CategorizerMessageOutput
from ..prompts import MESSAGE_CATEGORIZER_PROMPT
from langchain_anthropic import ChatAnthropic

load_dotenv()


def message_categorizer_agent():
    message_categorizer_prompt = PromptTemplate(
        template=MESSAGE_CATEGORIZER_PROMPT,
        input_variables=["message"]
    )

    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    
    return message_categorizer_prompt | llm.with_structured_output(CategorizerMessageOutput)