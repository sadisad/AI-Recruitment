import json
from groq import Groq
import os

class LanguageModel:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), 'groq_config_llm.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        self.client = Groq(api_key=config['api_key'])
        self.model = config['model']
    
    def generate_response(self, text):
        response = self.client.completions.create(
            prompt=text,
            model=self.model,
            max_tokens=150
        )
        return response['choices'][0]['text']
