from datetime import date, datetime
import time, os, json, requests, openai, warnings
from operator import itemgetter
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain.chains import create_sql_query_chain
from langchain_openai import ChatOpenAI
import openai
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import pandas as pd
from nltk.corpus import stopwords

class GPTEngine:
    def __init__(self):
        warnings.filterwarnings("ignore")
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        credentials = self.read_json_file('gpt_config.json')
        self.api_key, self.session_faq, openai.api_key = credentials['api_key'], {}, credentials['api_key']
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.indonesian_stopwords = stopwords.words('indonesian')
        self.response_config = {"model": credentials['model'],
                "temperature": credentials['temperature'],
                "top_p": credentials['top_p'],
                "frequency_penalty": credentials['frequency_penalty'],
                "presence_penalty": credentials['presence_penalty']}
    
    def read_json_file(self, file_name):
        f = open(self.dir_path + '\\' + file_name)
        file_content = json.load(f)
        f.close()
        return file_content
    
    def read_excel_file(self, file_name):
        df = pd.read_excel(self.dir_path + '\\' + file_name)
        return df
    
    def read_intro_prompt(self, file_name):
        f = open(self.dir_path + '\\' + file_name, "r", encoding="utf8")
        str_prompt = f.read()
        f.close()
        return str_prompt
    
    def initialize_interview(self):
        prompt = self.read_intro_prompt('prompts\\Interview\\interview_intro.txt')
        job_req = self.read_intro_prompt('prompts\\Interview\\job_requirement.txt')
        cv_dummy = self.read_intro_prompt('prompts\\Interview\\cv_string_dummy.txt')
        prompt = prompt.replace("<-> CV String <->", cv_dummy)
        prompt = prompt.replace("<-> Job Requirement <->", job_req)
        return prompt
    
    def initialize_form_filler(self):
        introductory = self.read_intro_prompt('prompts\\cv_reviewer.txt')
        prompt = introductory.replace('-- Prompt CV --', 
                                    self.read_intro_prompt('prompts\\Form Filler\\form_filler_intro.txt'))
        return prompt

    def initialize_redflags(self):
        introductory = self.read_intro_prompt('prompts\\cv_reviewer.txt')
        #------------
    #     prompt = introductory.replace('-- Prompt CV --', 
    #                                   self.read_intro_prompt('prompts\\Redflags\\redflags_intro_backup.txt'))

    #     turnover = '''Batas waktu yaitu {waktu}.
    # Jika ada masa kerja yang kurang dari {waktu}, berikan 'Red Flag'. Jika semua masa kerja lebih dari {waktu} maka 'Safe'.
    # Misal Durasi nya hanya berbeda sedikit, tetap berpatokan dengan {waktu} untuk Safe atau Red Flag nya.
    # Jika ada pengalaman kerja yang sama dengan {waktu}, itu masih belum 'Red Flag'.
    # Contoh, misal ada masa kerja yang hanya 1 bulan, berarti itu kan kurang dari batas waktu, maka 'Red Flag'.
    # Contoh lain, misal semua masa kerja di setiap posisi nya lebih dari batas waktu, maka 'Safe'.'''.format(waktu = '1 Tahun')
        
    #     prompt = prompt.replace('--turnover--', turnover)
        #-------------
        redflag_keys = self.read_json_file('prompts\\Redflags\\redflag_config.json')

        str_redflag = ''
        for list_item in redflag_keys:
            if list_item['enabled'].lower() == 'yes':
                str_redflag += list_item['title'] + ' (' + list_item['description'] + ') : '
                str_redflag += '\n--- Field Separator ---\n'

        prompt = introductory.replace('-- Prompt CV --', 
                                self.read_intro_prompt('prompts\\Redflags\\redflags_intro.txt'))
        
        prompt = prompt.replace('<-> Redflag Prompt <->', str_redflag)
        return prompt
    
    def initialize_cv_ranker(self):
        introductory = self.read_intro_prompt('prompts\\cv_reviewer.txt')
        prompt = introductory.replace('-- Prompt CV --', 
                                    self.read_intro_prompt('prompts\\CV Ranker\\cv_ranker_intro.txt'))
        return prompt
    
    def initialize_tehnical_test(self, tipe_test='live-coding'):

        dir_test = 'prompts\\Tehnical Test\\'
        prompt = self.read_intro_prompt(f'{dir_test}tehnical_test_intro.txt')
        
        if 'live' in tipe_test.lower() and 'coding' in tipe_test.lower():
            job_req = self.read_intro_prompt(f'{dir_test}Live Coding\\coding_test.txt')
            test_identifier = 'Berikan aku soal live coding logical untuk bidang berikut'
            code_or_not = self.read_intro_prompt(f'{dir_test}Live Coding\\live_coding_intro.txt')
        else:
            job_req = self.read_intro_prompt(f'{dir_test}Non IT\\non_it_test.txt')
            test_identifier = 'Ujilah aku dengan aku soal untuk job requirement berikut untuk bidang berikut'
            code_or_not = self.read_intro_prompt(f'{dir_test}Non IT\\non_it_intro.txt')

        prompt = prompt.replace("<-> Tehnical Test <->", job_req)
        prompt = prompt.replace('<-> Test Identifier <->', test_identifier)
        prompt = prompt.replace('<-> Code or Not <->', code_or_not)
        return prompt
    
    def initialize_one_cv_reviewer(self):
        introductory = self.read_intro_prompt('prompts\\cv_reviewer.txt')
        prompt = introductory.replace('-- Prompt CV --', 
                                    self.read_intro_prompt('prompts\\CV Reviewer (One CV)\\cv_reviewer_one_intro.txt'))
        return prompt
    
    def initialize_faq_langchain(self, session, db):
        faq_prompt = self.read_intro_prompt('prompts\\FAQ Functional\\faq_intro.txt')
        faq_lanjutan = self.read_intro_prompt('prompts\\FAQ Functional\\faq_lanjutan.txt')
        llm = ChatOpenAI(temperature=0, api_key=self.api_key, model='gpt-4')
        answer_prompt = PromptTemplate.from_template(faq_prompt)

        execute_query = QuerySQLDataBaseTool(db=db)
        query_writer = create_sql_query_chain(llm, db)
        answer_template = answer_prompt | llm | StrOutputParser()
    
        chain = (
            RunnablePassthrough
            .assign(query=query_writer)
            .assign(result=itemgetter("query") | execute_query) 
            | answer_template )
        
        self.session_faq[session['gpt_api_type']] = {'db': db, 
                                                    'chain' : chain, 
                                                    'query_writer' : query_writer,
                                                    'faq_lanjutan' : faq_lanjutan}

    def answer_faq_langchain(self, question, session):
        db = self.session_faq[session['gpt_api_type']]['db']
        chain = self.session_faq[session['gpt_api_type']]['chain']
        query_writer = self.session_faq[session['gpt_api_type']]['query_writer']
        faq_lanjutan = self.session_faq[session['gpt_api_type']]['faq_lanjutan']

        dict_question = {"question": question}
        question_lanjutan = faq_lanjutan.replace('-- question --', question)

        for i in range(5):

            try:
                response = chain.invoke(dict_question)
                query = query_writer.invoke(dict_question)
                query_result = str(db.run(query))
            except Exception as e:
                print(e)
                # dict_question = {"question": question_lanjutan + '\nBerikan query berikut : ' + str(e)}
                continue

            print('--- FAQ Answer ---')
            print('Question :', question)
            print('Answer :', response)
            print('--- FAQ Query ---\n'+str(query))
            print('Result Query : ' + query_result + '\n---- END ----')

            if query_result:
                return response
            
            dict_question = {"question": question_lanjutan}
            print('Asking another question... Please wait.')
            
        return 'Mohon maaf sebelumnya, saya tidak dapat memahami pertanyaan Anda dengan jelas. Untuk mendapatkan bantuan lebih lanjut, silakan menghubungi administrator. Apakah ada pertanyaan lain yang bisa saya bantu?'

    def answer_faq_assistant(self, method, question='', thread=''):

        if method == 'get':
            thread = openai.beta.threads.create()
            return thread
        else:

            for i in range(5):
                openai.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=question + '\nJangan lupa, format jawabanmu dalam tag HTML seperti <p> atau <li>.',
                )

                run = openai.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id='asst_5ZPcosI8OYHubcPmewn5imti'
                )

                print('Retrieving Message..')
                while run.status != "completed":
                    keep_retrieving_run = openai.beta.threads.runs.retrieve(
                        thread_id=thread.id,
                            # thread_id='thread_n38dAhnpcEWRfRK6st9hZWSB',
                        run_id=run.id
                    )
                    # print(f"Run status: {keep_retrieving_run.status}")

                    if keep_retrieving_run.status == "completed":
                        break

                all_messages = openai.beta.threads.messages.list(
                    thread_id=thread.id
                )

                all_messages = json.loads(all_messages.json())
                result = ''

                for item in all_messages['data']:
                    if item["role"] == "user":
                        break
                    for content in item["content"]:
                        result += content["text"]["value"]

                
                if '--- No Answer ---' not in result and 'apakah ada pertanyaan lain yang bisa saya bantu?' not in result.lower() and 'tidak ditemukan dalam FAQ' not in result.lower():
                    break
                else:
                    result = 'Mohon maaf sebelumnya, saya tidak dapat memahami pertanyaan Anda dengan jelas. Untuk mendapatkan bantuan lebih lanjut, silakan menghubungi administrator. Apakah ada pertanyaan lain yang bisa saya bantu?'

            return result

    def initialize_faq_cosine(self):
        path_prompt_faq = 'prompts\\FAQ Functional\\faq_cosine_'
        starting_prompt = self.read_intro_prompt(path_prompt_faq + 'intro.txt')
        self.faq_cosine_above_threshold = self.read_intro_prompt(path_prompt_faq + 'above_threshold.txt')
        self.faq_cosine_below_threshold = self.read_intro_prompt(path_prompt_faq + 'below_threshold.txt')
        self.faq_cosine_false_response = self.read_intro_prompt(path_prompt_faq + 'false.txt')
        self.faq_cosine_true_response = self.read_intro_prompt(path_prompt_faq + 'true.txt')

        faq_data = self.read_excel_file('prompts\\FAQ Functional\\faq.xlsx')
        self.faq_questions, self.faq_answers = faq_data['Question'], faq_data['Answer']
        self.question_vectorizer_id = TfidfVectorizer(stop_words=self.indonesian_stopwords)
        self.vectorized_questions_id = self.question_vectorizer_id.fit_transform(self.faq_questions)

        return starting_prompt
    
    def faq_cosine_similarity(self, user_query, rank_default=5):
        query_vec = self.question_vectorizer_id.transform([user_query]) ## --> Embeding gantii disini
        similarities = cosine_similarity(query_vec, self.vectorized_questions_id)
        
        # argsort sorts the indices based on the similarity scores in descending order
        sorted_indices = np.argsort(similarities[0])[::-1]    # Initialize the results dictionary
        results = []

        for rank, idx in enumerate(sorted_indices, start=1): 
            temp_dict = {
                'rank' : rank,
                'question': self.faq_questions.iloc[idx],
                'answer': self.faq_answers.iloc[idx],
                'similarity_score': similarities[0][idx]
            }

            results.append(temp_dict)
            
            if rank == rank_default:
                break

        # if results[0]['similarity_score'] > 0.3 :
        #     # text_result = 'Berikut adalah cara nya :\n' + results[0]['answer']
        #     text_result = self.faq_cosine_above_threshold.replace('<-> User Question <->', user_query)
        #     text_result = text_result.replace('<-> FAQ Question <->', results[0]['question'])
        #     question_list = results[0]['question']
        # else:
        list_cosine, question_str = [], ''

        for idx, i in enumerate(results, 0):
            question_str += str(idx) + ' - ' + i['question'] + '\n'
            list_cosine.append({'question' : i['question'], 'answer' : i['answer']})

        text_result = self.faq_cosine_below_threshold.replace('<-> User Question <->', user_query)
        text_result = text_result.replace('<-> FAQ Question <->', question_str)

        # return results
        # return text_result
        return text_result, list_cosine, question_str
    
    def hit_gpt_api(self, session, one_time_message=''):

        if one_time_message == '' :
            self.response_config['messages'] = session['interview_transcript']
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
    
    # ====
    # ====
    def format_response_gpt(self, session, answer):

        dict_form = {}

        if 'Interview' in session['gpt_api_type'] :
            answer, dict_form = self.format_interview(answer, str(session['interview_transcript']))

        elif '--- Field Separator ---' in answer and 'Redflags' in session['gpt_api_type'] :
            dict_form = self.format_redflags(answer)
        
        elif '--- Field Separator ---' in answer and 'Form Filler' in session['gpt_api_type'] :
            dict_form = self.format_form_filler(answer)

        elif '--- Field Separator ---' in answer and 'CV Ranker' in session['gpt_api_type'] :
            dict_form = self.format_cv_ranker(answer)
        
        elif 'Tehnical' in session['gpt_api_type'] :
            answer, dict_form = self.format_tehnical_test(answer, str(session['interview_transcript']))
        
        elif '--- Field Separator ---' in answer and 'One CV Reviewer' in session['gpt_api_type'] :
            dict_form = self.format_one_cv_reviewer(answer)
            dict_form['fk_job_id'] = session['job_id']
            dict_form['Job Title'] = session['job_title']

        elif 'Cosine' in session['gpt_api_type'] :
            answer, dict_form = self.format_faq_cosine(answer, session)

        return dict_form, answer
    
    def format_faq_cosine(self, answer, session):
        dict_form = {'chat_history' : str(session['interview_transcript'])}

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

    def format_interview(self, answer, chat_transcript):
        dict_form = {'chat_history' : str(chat_transcript),
            'NAMA' : '',
            'KELEBIHAN' : '', 
            'KEKURANGAN' : '', 
            'SKOR' : '', 
            'STATUS' : '',
            'ALASAN' : ''}

        if '--- SELESAI INTERVIEW ---' in answer:
            result = answer.replace('--- SELESAI INTERVIEW ---', '').split('--- Field Separator ---')

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
                    i = i.split(' : ', 1)
                    dict_form[key] = i[-1].strip('\n').strip()
                    break
        
        return answer, dict_form
    
    def format_redflags(self, answer):
        result = answer.split('--- Field Separator ---')
        # dict_form = {'Name' : '', 
        #             'Employment Overlap' : '', 
        #             'Employment Gap' : '', 
        #             'High Turnover' : '', 
        #             'Non-Progressive Career Path' : '', 
        #             'Inconsistent Career Path' : '',
        #             'Absence of Organization Activity' : '', 
        #             'Absence of Endorsement/Reference' : ''
        #             }
        
        # for i in result:
        #     for key, value in dict_form.items():
        #         if key.lower() in i.lower():
        #             i = i.split(':', 1)

        #             if 'Safe' in i[-1]:
        #                 dict_form[key] = 'Safe'
        #             else:
        #                 dict_form[key] = i[-1].strip('\n').strip()
                    
        #             break

        redflag_keys = self.read_json_file('prompts\\Redflags\\redflag_config.json')
        titles = [{
        "enabled" : "yes",
        "title": "Name",
        }] + redflag_keys
        dict_form = {}
        
        for i in result:
            for t in titles:
                enabled, key = t['enabled'], t['title']

                if enabled.lower() != 'yes' and key not in dict_form:
                    dict_form[key] = ''
                    dict_form[key + '_desc'] = ''


                if key.lower() in i.lower():
                    i = i.split(':', 1)

                    dict_form[key] = ''
                
                    if key != 'Name' :
                        dict_form[key + '_desc'] = ''

                    if key == 'Name':
                        dict_form[key] = i[-1].strip('\n').strip()

                    elif 'Safe' in i[-1]:
                        dict_form[key] = 'Safe'
                        dict_form[key + '_desc'] = '-'
                    else:
                        status, desc = i[-1].split('<->')
                        dict_form[key] = status.strip('\n').strip()
                        dict_form[key + '_desc'] = desc.strip('\n').strip()
            
                    break
            

        return dict_form
    
    def format_form_filler(self, answer):
        result = answer.split('--- Field Separator ---')
        dict_form = {'Name' : '', 
                    'Current Job Title' : '', 
                    'Summary' : '', 
                    'Phone Number' : '', 
                    'Birth Of Date' : '', 
                    'Address' : '',
                    'Email' : '', 
                    'Experiences' : '', 
                    'Educations' : '', 
                    'Projects/Portfolios' : '', 
                    'Certifications' : '',
                    'Awards' : '', 
                    'Publications' : '', 
                    'Volunteers' : '', 
                    'Languages' : ''
        }
        
        for i in result:
            for key, value in dict_form.items():
                if key.lower() in i.lower() and dict_form[key] == '':
                    i = i.split(' : ', 1)
                    dict_form[key] = i[-1].strip('\n').strip()
                    break

        return dict_form
    
    def format_cv_ranker(self, answer):
        result = answer.split('--- Field Separator ---')
        dict_form = {'Job Title' : '', 
                    'Job Requirement' : '', 
                    'RANK 1' : '', 
                    'RANK 2' : '', 
                    'RANK 3' : '', 
                    'RANK LAINNYA' : ''}
        
        for i in result:
            for key, value in dict_form.items():
                if key.lower() in i.lower() and dict_form[key] == '':
                    if 'RANK' in i:
                        i = i.split(key)
                    else:
                        i = i.split(':', 1)
                    dict_form[key] = i[-1].strip('\n').strip()
                    break
                elif 'RANK' in i and dict_form['RANK 1'] != '' and dict_form['RANK 2'] != '' and dict_form['RANK 3'] != '':
                    dict_form['RANK LAINNYA'] += i + '\n----'
                    break

        return dict_form
    
    def format_tehnical_test(self, answer, chat_transcript):
        dict_form = {'chat_history' : str(chat_transcript),
            'SKOR' : '',
            'STATUS' : '',
            'KESIMPULAN' : ''}

        if '--- PENILAIAN ---' in answer:
            result = answer.replace('--- PENILAIAN ---', '').split('--- Field Separator ---')

            if '--- PASS ---' in answer :
                dict_form['STATUS'] = 'PASS'
            elif '--- FAIL ---' in answer :
                dict_form['STATUS'] = 'FAIL'
                
            answer = 'Sesi hari ini memberikan kami gambaran yang baik tentang kemampuan Anda. Terima kasih telah berbagi keahlian Anda dengan kami. Kami akan segera kembali kepada Anda dengan informasi lebih lanjut mengenai proses seleksi.'
        else:
            return answer, dict_form

        for i in result:
            for key, value in dict_form.items():
                if key.lower() in i.lower() and dict_form[key] == '':
                    i = i.split(' : ', 1)
                    dict_form[key] = i[-1].strip('\n').strip()
                    break
        
        return answer, dict_form
    
    def format_one_cv_reviewer(self, answer):
        result = answer.split('--- Field Separator ---')
        dict_form = {'fk_job_id' : '',
                    'Job Title' : '',
                    'Name' : '',
                    'Total Masa Kerja Relevan' : '',
                    "Skills" : '',
                    "Kelebihan" : '',
                    "Kekurangan" : '',
                    "Final_-_Score" : '',
                    "Alasan" : '',
                    "Kesimpulan" : ''
                    }
        
        for i in result:
            for key, value in dict_form.items():
                if key.lower() in i.lower() and dict_form[key] == '':
                    i = i.split(' : ', 1)
                    dict_form[key] = i[-1].strip('\n').strip()
                    break

        return dict_form
    
# x = GPTEngine()
# z = x.initialize_redflags()
# print(z)