from langchain.llms import OpenAI

from langchain.chat_models import ChatOpenAI
from langchain.schema import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

class DavinciAgent:
    def __init__(self, temperature=0.9) -> None:
        self.llm = OpenAI(temperature=temperature)
    def predict(self, text: str) -> str:
        return self.llm.predict(text)
    
class GPTAgent:
    def __init__(self, temperature=0) -> None:
        self.chat = ChatOpenAI(temperature=temperature, model="gpt-3.5-turbo")
    def predict(self, text: str) -> str:
        return self.chat.predict_messages([HumanMessage(content=text)]).content