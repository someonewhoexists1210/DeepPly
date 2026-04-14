from openai import OpenAI
import os
from pydantic import BaseModel
from .classes import GameAnalysisResult


# API_KEY = os.getenv('OPENAI_API_KEY')
# if not API_KEY:
#     raise RuntimeError("OpenAI API key not added")

# client = OpenAI(api_key=API_KEY, timeout=30, max_retries=1)

# response = client.responses.create(
#     model="gpt-4.1-nano-2025-04-14",
#     prompt={
#         'id': "",
#         'variables': {},
#         'version': ""
#     },
#     temperature=0.1
# )


def generate_explanations(analysis: GameAnalysisResult):
    pass