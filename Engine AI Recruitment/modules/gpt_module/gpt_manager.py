from datetime import date, datetime
import time, os, json, requests, warnings
from operator import itemgetter
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain.chains import create_sql_query_chain
from langchain_openai import ChatOpenAI
import openai, ast
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import pandas as pd
from nltk.corpus import stopwords
from groq import Groq
import ast 
import json
import re

class GPTEngine:
    def __init__(self):
        warnings.filterwarnings("ignore")
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        credentials = self.read_json_file('gpt_config.json')
        self.groq_config = self.read_json_file('groq_config.json')
        self.groq_client = Groq(api_key=self.groq_config['api_key'])
        self.api_key, self.session_faq, openai.api_key = credentials['api_key'], {}, credentials['api_key']
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.response_config = {"model": credentials['model'],
                "temperature": credentials['temperature'],
                "top_p": credentials['top_p'],
                "frequency_penalty": credentials['frequency_penalty'],
                "presence_penalty": credentials['presence_penalty']}
    
    def read_json_file(self, file_name):
        f = open(self.dir_path + '/' + file_name)
        file_content = json.load(f)
        f.close()
        return file_content
    
    def read_excel_file(self, file_name):
        df = pd.read_excel(self.dir_path + '/' + file_name)
        return df
    
    def hit_groq_api(self, session, one_time_message=''):
        if one_time_message == '' :
            self.response_config['messages'] = session['history']
        else:
            self.response_config['messages'] = [{"role": "system", "content" : one_time_message}]
        
        response = self.groq_client.chat.completions.create(
            messages=self.response_config['messages'],
            model=self.groq_config['model']
        )

        json_response = json.loads(response.json())
        
        try:
            answer = json_response.get("choices")[0].get("message")["content"]
        except:
            answer = 'Maaf, saya mengalami kesalahan. Bisa diulang kembali?'
        
        return answer, json_response
    
    def hit_gpt_api(self, session, one_time_message=''):

        if one_time_message == '' :
            self.response_config['messages'] = session['history']
        else:
            self.response_config['messages'] = [{"role": "system", "content" : one_time_message}]

        try:
            response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)
        except:
            time.sleep(3)
            response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)

        for i in range(3):
            json_response = response.json()

            if 'error' in json_response:
                if 'please try again in' in json_response['error']['message'].lower():
                    time.sleep(int(i) * 10) # Handle Limit
                    response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)
                elif 'request too large for' in json_response['error']['message'].lower():
                    answer = "Error, please contact administrator."
                    return answer, json_response
            else:
                break

        try:
            answer = json_response.get("choices")[0].get("message")["content"]
        except:
            answer = 'Maaf, saya mengalami kesalahan. Bisa diulang kembali?'
        
        return answer, json_response
    
    def read_intro_prompt(self, file_name):
        f = open(self.dir_path + '/' + file_name, "r", encoding="utf8")
        str_prompt = f.read()
        f.close()
        return str_prompt
    
    def format_response_gpt(self, session, answer):
        dict_form = {}

        if 'Interview' in session['gpt_api_type']:
            answer, dict_form = self.format_interview(answer, session)

        elif '--- Field Separator ---' in answer:
            if 'Redflags' in session['gpt_api_type']:
                dict_form = self.format_candidate_redflags(answer)
            
            elif 'Form Filler' in session['gpt_api_type']:
                dict_form = self.format_form_filler(answer)

            elif 'Profile Matching' in session['gpt_api_type']:
                dict_form = self.format_profile_matching(answer)
                
            elif 'Candidate Ranker' in session['gpt_api_type']:
                dict_form = self.candidate_ranker_formatting(answer)
                
            elif 'Questions' in session['gpt_api_type']:
                dict_form = self.format_interview_question(answer, session)
        return dict_form, answer
    
    def initialize_form_filler(self):
        introductory = self.read_intro_prompt('prompts/cv_reviewer.txt')
        prompt = introductory.replace('-- Prompt CV --', self.read_intro_prompt('prompts/Form Filler/form_filler_intro.txt'))
        return prompt

    def initialize_candidate_redflags(self):
        introductory = self.read_intro_prompt('prompts/cv_reviewer.txt')
        redflag_keys = self.read_json_file('prompts/Redflags/redflag_config.json')

        str_redflag = ''
        for list_item in redflag_keys:
            if list_item['enabled'].lower() == 'yes':
                str_redflag += list_item['title'] + ' (' + list_item['description'] + ') : '
                str_redflag += '\n--- Field Separator ---\n'

        prompt = introductory.replace('-- Prompt CV --', 
                                self.read_intro_prompt('prompts/Redflags/redflags_intro.txt'))
        
        prompt = prompt.replace('<-> Redflag Prompt <->', str_redflag)
        return prompt
    
    def format_candidate_redflags(self, answer):
        
        result = answer.split('--- Field Separator ---')
        dict_form = {}
        redflag_counter, all_status_counter = 0, 0

        for i in result:
            if i == '' or i == False:
                continue

            if 'Here is' in i and 'evaluation' in i:
                i = i.split('\n')
                temp_str = ''

                for j in i:
                    if 'name' in j.lower() and ':' in j:
                        temp_str = j

                i = temp_str

            # Safely attempt to split the line
            if ':' in i:
                key, value = i.split(':', 1)  # Only split on the first colon
                key, value = key.strip('\n').strip(), value.strip('\n').strip()

                if 'name' in key.lower():
                    dict_form['name'] = value
                elif 'safe' in value.lower():
                    all_status_counter += 1
                    dict_form[key] = {"status": 'Safe', "desc": '-'}
                else:
                    all_status_counter += 1
                    redflag_counter += 1
                    status, desc = value.split('<->', 1)
                    status = status.strip('\n').strip()
                    desc = desc.strip('\n').strip()
                    dict_form[key] = {"status": 'Red Flag', "desc": desc}

        dict_form['redflag_percentage'] = str(round((redflag_counter / all_status_counter), 2) * 100) + '%'
        return dict_form

    def format_form_filler(self, answer):
        dict_form = {}
        result = answer.split('--- Field Separator ---')

        for i in result:

            if i:
                key, value = i.split(':', 1)
                key, value = key.strip('\n').strip(), value.strip('\n').strip()
    
                try:
                    dict_form[key] = ast.literal_eval(value)
                except:
                    dict_form[key] = value

        return dict_form
    
    def format_profile_matching(self, answer):
        result = answer.split('--- Field Separator ---')
        dict_form = {
            'name': '',
            'total_masa_kerja_relevan': '',
            "skills": '',
            "kelebihan": '',
            "kekurangan": '',
            "skor_cv": '',
            "alasan": '',
            "kesimpulan": '',
            "kesesuaian": '',
            "kriteria_pekerjaan": '',
            'suggestion': '' 
        }

        for i in result:
            for key in dict_form.keys():
                if key.replace('_', ' ') in i.lower() and dict_form[key] == '':
                    try:
                        parts = i.split(':', 1)
                        if len(parts) > 1:
                            value = parts[1].strip()
                        else:
                            value = ""

                        if key == 'total_masa_kerja_relevan':
                            try:
                                dict_form[key] = ast.literal_eval(value)
                            except (ValueError, SyntaxError):
                                dict_form[key] = json.loads(value)  # If it's already a JSON string, load it
                        elif key == 'skor_cv':
                            dict_form[key] = value
                        else:
                            try:
                                dict_form[key] = ast.literal_eval(value)
                            except (ValueError, SyntaxError):
                                dict_form[key] = value
                    except ValueError:
                        continue

        return dict_form
    
    def initialize_candidate_ranker(self):
        introductory = self.read_intro_prompt('prompts/cv_reviewer.txt')
        prompt = introductory.replace('-- Prompt CV --', 
                                    self.read_intro_prompt('prompts/CV Ranker/cv_ranker_intro.txt'))
        return prompt
    
    def candidate_ranker_formatting(self, llm_response):
        result = {}

        result['ranking'] = self.candidate_ranker_parse(llm_response, 'Ranking', '\n')
        result['name'] = self.candidate_ranker_parse(llm_response, 'Name :', '\n')
        result['total_masa_kerja_relevan'] = self.candidate_ranker_parse(llm_response, 'Total Masa Kerja Relevan :', '\n')
        result['skills'] = self.candidate_ranker_parse(llm_response, 'Skills :', '\n')
        result['kelebihan'] = self.candidate_ranker_parse(llm_response, 'Kelebihan :', '\n')
        result['kekurangan'] = self.candidate_ranker_parse(llm_response, 'Kekurangan :', '\n')
        result['skor'] = self.candidate_ranker_parse(llm_response, 'Skor :', '\n')
        result['alasan'] = self.candidate_ranker_parse(llm_response, 'Alasan :', '\n')
        result['kesimpulan'] = self.candidate_ranker_parse(llm_response, 'Kesimpulan :', '\n')
        result['job_title'] = self.candidate_ranker_parse(llm_response, 'Job Title :', '\n')
        result['job_requirements'] = self.candidate_ranker_parse(llm_response, 'Job Requirements :', '\n')

        return result

    def candidate_ranker_parse(self, text, start, end):
        try:
            pattern = re.escape(start) + r'\s*([\s\S]*?)\s*' + re.escape(end)
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
            else:
                return 'Tidak tersedia'
        except Exception as e:
            return 'Tidak tersedia'
    
    def initialize_candidate_profile_matching(self):
        introductory = self.read_intro_prompt('prompts/cv_reviewer.txt')
        prompt = introductory.replace('-- Prompt CV --', 
                                    self.read_intro_prompt('prompts/Profile Matching/initialize_profile_matching.txt'))
        return prompt
    
# ---------------------------------------------- Interview ---------------------------------------------------
    
    def initialize_interview(self, str_cv='', str_job_req=''):
        current_hour = datetime.now().hour
        
        if 5 <= current_hour < 12:
            greeting = "Selamat pagi"
        elif 12 <= current_hour < 15:
            greeting = "Selamat siang"
        elif 15 <= current_hour < 18:
            greeting = "Selamat sore"
        else:
            greeting = "Selamat malam"
        
        prompt = self.read_intro_prompt('prompts/Interview/interview_intro.txt')
        job_req = self.read_intro_prompt('prompts/Interview/job_requirement.txt')
        cv_dummy = self.read_intro_prompt('prompts/Interview/cv_string_dummy.txt')
        prompt = prompt.replace('<-> waktu saat ini <->', greeting)
        
        if str_cv == '':
            prompt = prompt.replace("<-> CV String <->", cv_dummy)
        else:
            prompt = prompt.replace("<-> CV String <->", str_cv)

        if str_job_req == '':
            prompt = prompt.replace("<-> Job Requirement <->", job_req)
        else:
            prompt = prompt.replace("<-> Job Requirement <->", str_job_req)

        return prompt
    
    def initialize_generate_question(self):
        introductory = self.read_intro_prompt('prompts/question_generator.txt')
        prompt = introductory.replace('<-> Form Fields <->', 
                                        self.read_intro_prompt('prompts/Interview Question/interview_question_intro.txt'))
        return prompt

    def format_interview(self, answer, chat_transcript):
        dict_form = {
            'NAMA' : '',
            'KELEBIHAN' : '', 
            'KEKURANGAN' : '', 
            'SKOR' : '', 
            'STATUS' : '',
            'ALASAN' : ''}

        if '--- WAWANCARA SELESAI ---' in answer:
            result = answer.replace('--- WAWANCARA SELESAI ---', '').split('--- Field Separator ---')

            if '--- PASS ---' in answer :
                dict_form['STATUS'] = 'PASS'
            elif '--- FAIL ---' in answer :
                dict_form['STATUS'] = 'FAIL'
                
            answer = 'Sesi interview hari ini telah berakhir, dan saya ingin mengucapkan terima kasih atas waktu dan kesediaan Anda untuk berbagi tentang diri Anda serta pengalaman yang relevan dengan posisi yang kami tawarkan. Kami sangat terkesan dengan latar belakang dan keahlian Anda. Kami akan segera memproses semua informasi yang telah kami kumpulkan dari semua kandidat dan mengambil keputusan dalam waktu dekat. Kami berharap dapat memberi kabar lebih lanjut kepada Anda mengenai hasil seleksi ini. Sekali lagi, terima kasih telah meluangkan waktu Anda dan semoga kita bisa bekerja sama di masa depan.'
        else:
            return answer, dict_form

        for i in result:
            for key, value in dict_form.items():
                if key.lower() in i.lower() and dict_form[key] == '':
                    i = i.split(':', 1)
                    dict_form[key] = i[-1].strip('\n').strip()
                    break
        
        return answer, dict_form
    
    def format_interview_question(self, answer):
        dict_form = {
            'job_title': '',
            'questions': []
        }
        
        result = answer.split('--- Field Separator ---')
        
        for i in result:
            if i:
                parts = i.split(':', 1)
                if len(parts) == 2:
                    key, value = parts
                    key, value = key.strip('\n').strip(), value.strip('\n').strip()
                    if 'Job Title' in key:
                        dict_form['job_title'] = value.lower()
                    else:
                        question_num = key.lower()
                        question_text = value
                        question = {question_num: question_text}
                        dict_form['questions'].append(question)
                        
        return dict_form
