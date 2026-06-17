from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv
from ..prompts import DESKIA
from langchain_anthropic import ChatAnthropic

load_dotenv()


def categorize_email():
    email_categorizer_prompt = PromptTemplate(
        template=DESKIA,
        input_variables=["email"]
    )
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    pass