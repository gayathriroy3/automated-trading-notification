from agents.llm.gemini_client import MODEL
from agents.llm.gemini_client import client

response = client.models.generate_content(
    model=MODEL,
    contents="Say hello"
)
print(response.text)