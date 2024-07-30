import json
from groq import Groq
import ast
import os
from datetime import datetime

class LanguageModel:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), 'groq_config_llm.json')
        with open(config_path, 'r') as f:
            self.configllm = json.load(f)
        self.client = Groq(api_key=self.configllm['api_key'])
        self.model = self.configllm['model']
        
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
    
    def generate_response(self, text):
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": text
                }
            ],
            model=self.configllm['model']
        )
        
        message = chat_completion.choices[0].message.content
        
        
        # dict_form = self.format_response(message)
        dict_form = ''
        
        return message, dict_form
    
    def read_intro_prompt(self, file_name):
        f = open(self.dir_path + '/' + file_name, "r", encoding="utf8")
        str_prompt = f.read()
        f.close()
        return str_prompt
    
    def initialize_prompt(self):
        current_time = datetime.now().time()
        prompt = self.read_intro_prompt('prompt/intro_prompt.txt')
        # prompt = prompt.replace('<-----command----->', command)
        prompt = prompt.replace('<->waktu saat ini<->', str(current_time))
        return prompt
    
    def format_response(self, response):
        dict_form = {}
        result = response.split('--- Field Separator ---')

        for i in result:

            if i:
                key, value = i.split(':', 1)
                key, value = key.strip('\n').strip(), value.strip('\n').strip()
    
                try:
                    dict_form[key] = ast.literal_eval(value)
                except:
                    dict_form[key] = value

        return dict_form
        