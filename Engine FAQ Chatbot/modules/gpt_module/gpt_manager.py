from datetime import date, datetime
import time, os, json, requests, openai, warnings
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

class GPTEngine:
    def __init__(self):
        warnings.filterwarnings("ignore")
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        credentials = self.read_json_file('gpt_config.json')
        self.groq_config = self.read_json_file('groq_config.json')
        self.groq_client = Groq(api_key=self.groq_config['api_key'])
        self.api_key, self.session_faq, openai.api_key = credentials['api_key'], {}, credentials['api_key']
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.indonesian_stopwords = stopwords.words('indonesian')
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
    
    def read_intro_prompt(self, file_name):
        f = open(self.dir_path + '/' + file_name, "r", encoding="utf8")
        str_prompt = f.read()
        f.close()
        return str_prompt
    
    def initialize_faq_cosine(self):
        path_prompt_faq = 'prompts/FAQ Functional/faq_cosine_'
        starting_prompt = self.read_intro_prompt(path_prompt_faq + 'intro.txt')
        
        current_time_str = datetime.now().time().strftime("%H:%M:%S")
        starting_prompt += '\n------\ncurrent time:\n' + current_time_str
        
        self.faq_cosine_below_threshold = self.read_intro_prompt(path_prompt_faq + 'below_threshold.txt')
        self.faq_cosine_false_response = self.read_intro_prompt(path_prompt_faq + 'false.txt')
        self.faq_cosine_true_response = self.read_intro_prompt(path_prompt_faq + 'true.txt')
        self.faq_chat_manual = self.read_intro_prompt('prompts/FAQ Functional/faq_knowledge_from_manual_chat.txt')

        faq_data = self.read_excel_file('prompts/FAQ Functional/faq.xlsx')
        self.faq_questions, self.faq_answers, self.faq_module = faq_data['Question'], faq_data['Answer'], faq_data['Module']
        self.question_vectorizer_id = TfidfVectorizer(stop_words=self.indonesian_stopwords)
        self.vectorized_questions_id = self.question_vectorizer_id.fit_transform(self.faq_questions)

        return starting_prompt
    
    def faq_cosine_similarity(self, user_query, rank_default=5):
        query_vec = self.question_vectorizer_id.transform([user_query])
        similarities = cosine_similarity(query_vec, self.vectorized_questions_id)
        
        sorted_indices = np.argsort(similarities[0])[::-1]
        results = []

        for rank, idx in enumerate(sorted_indices, start=1): 
            temp_dict = {
                'rank': rank,
                'module': self.faq_module.iloc[idx],
                'question': self.faq_questions.iloc[idx],
                'answer': self.faq_answers.iloc[idx],
                'similarity_score': similarities[0][idx]
            }
            results.append(temp_dict)
            if rank == rank_default:
                break

        list_cosine, question_str = [], ''
        for idx, i in enumerate(results, 0):
            question_str += str(idx) + ' - ' + i['question'] + '\n'
            list_cosine.append({
                'module': i['module'], 
                'question': i['question'], 
                'answer': i['answer'], 
                'similarity_score': i['similarity_score']
            })

        text_result = self.faq_cosine_below_threshold.replace('<-> User Question <->', user_query)
        text_result = text_result.replace('<-> FAQ Question <->', question_str)

        return text_result, list_cosine, question_str
    
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
        
        # print(answer)
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
            print('<<< ' + session['gpt_api_type'] + ' >>>')
            print(json_response)
            print('==========')

            if 'error' in json_response:

                if 'please try again in' in json_response['error']['message'].lower():
                    print('Sleeping, Limit.')
                    print('==========')
                    time.sleep(int(i) * 10) # Handle Limit
                    response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)
                elif 'request too large for' in json_response['error']['message'].lower():
                    print('Limit, harus dihapus chat history nya.')
                    print('==========')
                    # answer = "Limit, harus dihapus chat history nya. To Be Fixed. Mungkin Chatnya Harus Dihapus."
                    answer = "Error, please contact administrator."
                    return answer, json_response
            else:
                break

        try:
            answer = json_response.get("choices")[0].get("message")["content"]
        except:
            answer = 'Maaf, saya mengalami kesalahan. Bisa diulang kembali?'
        
        return answer, json_response
    
    def format_response_gpt(self, session, answer):

        dict_form = {}
    
        if 'Cosine' in session['gpt_api_type'] :
            answer, dict_form = self.format_faq_cosine(answer, session)
        elif 'Knowledge' in session['gpt_api_type']:
            answer, dict_form = self.format_manual_knowledge(answer, session)

        return dict_form, answer

    def format_faq_cosine(self, answer, session):
        dict_form = {'chat_history' : str(session['history'])}

        if '<--->' in answer and 'Pertanyaan' in answer:
            pass
        elif '--- TIDAK ---' in answer:
            answer = self.faq_cosine_false_response.replace('<-> Question User <->', session['user_question'])
            answer = answer.replace('<-> Question FAQ <->', session['question_str'])
        
        elif '---' in answer :
            idx_answer = int(answer.replace('---', '').strip())
            answer = self.faq_cosine_true_response.replace('<-> Question FAQ <->', session['list_cosine'][idx_answer]['question'])
            answer = answer.replace('<-> Answer FAQ <->', session['list_cosine'][idx_answer]['answer'])
        
        return answer, dict_form

    def format_manual_knowledge(self, answer, session):
        result = (answer).split('--- Field Separator ---')
        list_question, list_answer = [], []

        for i in result:
            question_section = i.split('\n')
            for j in question_section:
                if 'Question : ' in j:
                    list_question.append(j.replace('Question :', '').strip())
                
                if 'Jawaban : ' in j:
                    list_answer.append(j.replace('Jawaban :', '').strip())

        dict_form = {'Question': list_question,
                                'Answer': list_answer}
        
        df = pd.DataFrame(dict_form)
        
        datatoexcel = pd.ExcelWriter(self.dir_path + '/prompts/FAQ Functional/Manual Knowledge.xlsx')
        df.to_excel(datatoexcel, sheet_name='Knowledge')
        datatoexcel.close()

        print('Knowlegde Written Successfully.')
        
        return dict_form, dict_form
    
    def intialize_sentiment_analysis(self, list_of_sentiment):
        introductory = self.read_intro_prompt('prompts/FAQ Functional/sentiment_analysis.txt')
        introductory += '\n------\n' + list_of_sentiment
    
        return introductory
    
    def format_sentiment_analysis(self, answer):
        dict_form = {
            'positive': "",
            'negative': "",
            'neutral': "",
            'overallRating': '',
            'summary': ''
            }
        
        result = answer.split('--- Field Separator ---')
        
        for i in result:
            sentiment_section = i.split('\n')
            for j in sentiment_section:
                print(j)
                if 'Positive' in j:
                    dict_form['positive'] = (j.replace('Positive:', '').strip())
                
                if 'Negative' in j:
                    dict_form['negative'] = (j.replace('Negative:', '').strip())
                
                if 'Neutral' in j:
                    dict_form['neutral'] = (j.replace('Neutral:', '').strip())
                    
                if 'Overall Rating' in j:
                    dict_form['overallRating'] = j.replace('Overall Rating:', '').strip()
                
                if 'Summary' in j:
                    dict_form['summary'] = j.replace('Summary:', '').strip()
                    
        return dict_form
    
    def initialize_evaluate_user_question(self, chat_transcripts):
        path_prompt_faq = 'prompts/FAQ Functional/faq_evaluate_'
        starting_prompt = self.read_intro_prompt(path_prompt_faq + 'question.txt')
    
        starting_prompt += '\n------\n:\n' + chat_transcripts
        return starting_prompt
    
    def format_evaluate_user_question(self, answer):
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