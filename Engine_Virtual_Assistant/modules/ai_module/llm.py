from datetime import datetime
import json
import uuid
from flask import session
from groq import Groq
import ast
import os

from modules.file_processor_module.file_manager import FileHandler
from modules.db_module.db_manager import DatabaseOperations

fileManager = FileHandler()
dbManager = DatabaseOperations()

class LanguageModel:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), 'groq_config_llm.json')
        with open(config_path, 'r') as f:
            self.configllm = json.load(f)
        self.client = Groq(api_key=self.configllm['api_key'])
        self.model = self.configllm['model']
        
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        
    def hit_groq_api(self, session_data, one_time_message=''):
        prompt = [{"role": "system", "content": one_time_message}] if one_time_message else session_data['history']
                
        response = self.client.chat.completions.create(
            messages=session_data['history'],
            model=self.configllm['model']
        )

        json_response = json.loads(response.json())
        
        try:
            answer = json_response.get("choices")[0].get("message")["content"]
        except:
            answer = 'Maaf, saya mengalami kesalahan. Bisa diulang kembali?'
        
        return answer, json_response
    
    def generate_response(self, session_data, primary_key={}, additional_dict={}, one_time_message=''):
        
        answer, json_response = self.hit_groq_api(session_data, one_time_message)
        session_data['history'].append({"role": "system", "content": answer})
        
        log_file_content = fileManager.save_chat_transcript(session_data)
        dict_form = {**additional_dict}
        row_id = dbManager.store_to_db(session_data['gpt_api_type'].split('_')[0],
                                    session_data['bool_chat'],
                                    session_data['gpt_api_type'],
                                    log_file_content,
                                    dict_data=dict_form,
                                    id_dict=primary_key)
        
        
        return answer, session_data

    def initialize_api_type(self, api_type, session_data):
        current_time = datetime.now().strftime("%H-%M-%S")  # Replace colons with hyphens
        session_data['gpt_api_type'] =  api_type + '_' + str(uuid.uuid4()) + '_' +  current_time
    
    def read_intro_prompt(self, file_name):
        f = open(self.dir_path + '/' + file_name, "r", encoding="utf8")
        str_prompt = f.read()
        f.close()
        return str_prompt
    
    def initialize_prompt(self):
        current_time = datetime.now().strftime("%H-%M-%S")  # Replace colons with hyphens
        prompt = self.read_intro_prompt('prompt/intro_prompt.txt')
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

    def process_input(self, user_input, session_data):
        if "absen" in user_input.lower():
            return self.handle_absen(session_data)
        elif "approval" in user_input.lower():
            return self.handle_approval(session_data)
        elif "cuti" in user_input.lower():
            return self.handle_custom_request('pengajuan_cuti.txt', session_data)
        elif "sakit" in user_input.lower():
            return self.handle_custom_request('perizinan_sakit.txt', session_data)
        else:
            response, session_data = self.generate_response(session_data)
            return {"message": response}, session_data
    
    def handle_absen(self, session_data):
        response = self.read_payload('absen.txt')
        session_data['history'].append({"role": "system", "content": response})
        dbManager.upsert_conversation_transcript(session_data['gpt_api_type'], response, 'AI')
        return {"message": response}, session_data
    
    def handle_approval(self, session_data):
        response = self.read_payload('approval.txt')
        session_data['history'].append({"role": "system", "content": response})
        dbManager.upsert_conversation_transcript(session_data['gpt_api_type'], response, 'AI')
        return {"message": response}, session_data
    
    def handle_custom_request(self, filename, session_data):
        response = self.read_payload(filename)
        session_data['history'].append({"role": "system", "content": response})
        dbManager.upsert_conversation_transcript(session_data['gpt_api_type'], response, 'AI')
        return {"message": response}, session_data