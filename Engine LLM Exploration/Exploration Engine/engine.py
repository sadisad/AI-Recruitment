from flask import Flask, session, request, jsonify, render_template
from flask_session import Session
from flask_cors import CORS, cross_origin
import os, json, shutil, signal, sys
from datetime import date, datetime

module_dir = 'modules\\'
modules_path = ['db', 'file_processor', 'gpt']
for mp in modules_path:
    mp = 'modules\\' + mp + '_module\\' 
    if mp not in sys.path:
        sys.path.append(mp)

from db_manager import DatabaseOperations
from file_manager import FileHandler
from gpt_manager import GPTEngine

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "interview_session_folder"
Session(app)
cors = CORS(app)
db_ops = DatabaseOperations()
file_handler = FileHandler()
gpt_engine = GPTEngine()

def clear_sessions(signum, frame):
    session_dir = app.config["SESSION_FILE_DIR"]
    if os.path.isdir(session_dir):
        shutil.rmtree(session_dir)
        print("Session storage cleared.")
    os._exit(0)  # Use os._exit(0) to exit the application

# Register signal handler for SIGINT (CTRL+C) and SIGTERM
signal.signal(signal.SIGINT, clear_sessions)
signal.signal(signal.SIGTERM, clear_sessions)

def initialize_api_type(api_type):
    current_time = datetime.now().strftime("%H-%M-%S")
    session['gpt_api_type'] =  api_type + '_' + current_time + '_' + str(session.sid)

def check_upload_file(request_obj):
    
    file = request_obj.files.get('fileUpload')  # 'file' should match the 'name' attribute in your HTML file input
    if file:
        file_name = file.filename
        file_path = os.path.join(file_handler.dir_source, file_name)
        file.save(file_path)
        file_type, str_result = file_handler.checker_and_generator(file_name)
        file_handler.str_to_txt(file_type, file_name, str_result)
        user_response = str_result
    else:
        user_response = request.form['responseText']
    
    return user_response

def query_gpt(one_time_message=''):
    # return 'Dummy Response'
    answer, json_response = gpt_engine.hit_gpt_api(session, one_time_message)
    
    ## ====
    session['interview_transcript'].append({"role": "system", "content": answer})
    usage = json_response.get('usage', {})
    session['usage'].append(str(usage)) 
    ## ====
    
    log_file_content = file_handler.save_chat_transcript(session)
    dict_form, answer = gpt_engine.format_response_gpt(session, answer)
    db_ops.store_to_db(session['gpt_api_type'].split('_')[0], session['bool_chat'], session['gpt_api_type'], log_file_content, dict_form)

    return answer

@app.route('/')
@cross_origin()
def index():
    return render_template('index.html')

@app.route('/gpt_4')
@cross_origin()
def gpt_4():
    return render_template('chatbox.html',  page_title='GPT-4 API Simulation', post_get_route='/start_gpt_4')

@app.route('/interview_with_cv')
@cross_origin()
def interview_with_cv():
    return render_template('chatbox.html',  page_title='Interview Chat Simulation', post_get_route='/start_interview')

@app.route('/cv_form_filler')
@cross_origin()
def cv_form_filler():
    return render_template('chatbox.html',  page_title='CV Form Filler', post_get_route='/start_cv_form_filler')

@app.route('/cv_redflags')
@cross_origin()
def cv_redflags():
    return render_template('chatbox.html',  page_title='CV Redflags', post_get_route='/start_cv_redflags')

@app.route('/cv_ranker')
@cross_origin()
def cv_ranker():
    return render_template('chatbox.html',  page_title='CV Ranker', post_get_route='/start_cv_ranker')

@app.route('/tehnical_test')
@cross_origin()
def tehnical_test():
    return render_template('chatbox.html',  page_title='Tehnical Test / Live Coding', post_get_route='/start_tehnical_test')

@app.route('/one_cv_reviewer')
@cross_origin()
def one_cv_reviewer():
    return render_template('chatbox.html',  page_title='CV Reviewer (One CV)', post_get_route='/start_one_cv_reviewer')

@app.route('/faq_functional_langchain')
@cross_origin()
def faq_functional_langchain():
    return render_template('chatbox.html',  page_title='Chatbot FAQ Functional (Langchain)', post_get_route='/start_faq_functional_langchain')

@app.route('/faq_functional_assistant')
@cross_origin()
def faq_functional_assistant():
    return render_template('chatbox.html',  page_title='Chatbot FAQ Functional (Assistant)', post_get_route='/start_faq_functional_assistant')

@app.route('/faq_functional_cosine')
@cross_origin()
def faq_functional_cosine():
    return render_template('chatbox.html',  page_title='Chatbot FAQ Functional (Cosine)', post_get_route='/start_faq_functional_cosine')

@app.route('/start_gpt_4', methods=['GET', 'POST'])
@cross_origin()
def start_gpt_4():
    if request.method == 'GET' :    
        session['usage'], session['bool_chat'] = [], True
        initialize_api_type('Default GPT-4 Chat')
        session['interview_transcript'] = [{"role": "user", 
                            "content": '''Hai Chat!'''}]
        
        result = query_gpt()
    else:
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt() 

    return jsonify({"next_question": result})

@app.route('/start_interview', methods=['GET', 'POST'])
@cross_origin()
def start_interview():
    if request.method == 'GET' :
        session['usage'], session['bool_chat'] = [], True
        initialize_api_type('Interview')

        starting_prompt = gpt_engine.initialize_interview()
        session['interview_transcript'] = [{"role": "user", "content": starting_prompt}]
        result = query_gpt()
    else:
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt() 

    return jsonify({"next_question": result})

@app.route('/start_cv_form_filler', methods=['GET', 'POST'])
@cross_origin()
def start_cv_form_filler():

    if request.method == 'POST':
        session['usage'], session['bool_chat'] = [], False
        initialize_api_type('Form Filler')

        starting_prompt = gpt_engine.initialize_form_filler()
        session['interview_transcript'] = [{"role": "user", 
                                        "content": starting_prompt},  # Brainwash
                                        {"role" : "system", # Gua Kunci si GPT biar Paham
                                        "content" : "Halo, saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam mengisi form CV. Silakan berikan informasi yang diperlukan."},
                                        ]
        
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt() 
    else:
        result = 'Halo, saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam mengisi form CV. Silakan berikan informasi yang diperlukan.'

    return jsonify({"next_question": result})

@app.route('/start_cv_redflags', methods=['GET', 'POST'])
@cross_origin()
def start_cv_redflags():
    
    if request.method == 'POST':


        session['usage'], session['bool_chat'] = [], False
        initialize_api_type('Redflags')

        starting_prompt = gpt_engine.initialize_redflags()
        session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy('IT Developer')
        starting_prompt += '\n---\n---' + session['job_vacancy']

        session['interview_transcript'] = [{"role": "user", 
                                        "content": starting_prompt},
                                        {"role" : "system", 
                                        "content" : "Halo, saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam mengevaluasi CV dan menilai potensi red flag. Silakan berikan CV yang ingin Anda evaluasi."},
                                        ]
        
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt() 
    else:
        result = 'Halo, saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam mengevaluasi CV dan menilai potensi red flag. Silakan berikan CV yang ingin Anda evaluasi.'

    return jsonify({"next_question": result})

@app.route('/start_cv_ranker', methods=['GET', 'POST'])
@cross_origin()
def start_cv_ranker():
    
    if request.method == 'POST':

        session['usage'], session['bool_chat'] = [], False
        initialize_api_type('CV Ranker')

        starting_prompt = gpt_engine.initialize_cv_ranker()
        session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy('IT Developer')
        starting_prompt += '\n------\n' + session['job_vacancy']

        session['interview_transcript'] = [{"role": "user", 
                                        "content": starting_prompt},
                                        {"role" : "system", 
                                        "content" : "Halo! Saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam proses seleksi CV untuk posisi yang Anda butuhkan. Saya akan memberikan ranking, kesimpulan, kelebihan, kekurangan serta alasan untuk setiap CV yang Anda berikan berdasarkan job vacancy yang telah ditentukan. Saya juga akan mempertimbangkan total masa kerja relevan, skill, proyek, serta latar belakang pendidikan dalam penilaian saya. Mari kita mulai."},
                                        ]
        
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt() 
    else:
        result = 'Halo! Saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam proses seleksi CV untuk posisi yang Anda butuhkan. Saya akan memberikan ranking, kesimpulan, kelebihan, kekurangan serta alasan untuk setiap CV yang Anda berikan berdasarkan job vacancy yang telah ditentukan. Saya juga akan mempertimbangkan total masa kerja relevan, skill, proyek, serta latar belakang pendidikan dalam penilaian saya. Mari kita mulai.'

    return jsonify({"next_question": result})

@app.route('/start_tehnical_test', methods=['GET', 'POST'])
@cross_origin()
def start_tehnical_test():

    if request.method == 'GET':
        session['usage'], session['bool_chat'] = [], True
        initialize_api_type('Tehnical Test')

        starting_prompt = gpt_engine.initialize_tehnical_test('Live Coding')
        # starting_prompt = gpt_engine.initialize_tehnical_test('Non IT')
        session['interview_transcript'] = [{"role": "user", "content": starting_prompt}]
        result = query_gpt()
    else:
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt()
    
    return jsonify({"next_question": result})

@app.route('/start_one_cv_reviewer', methods=['GET', 'POST'])
@cross_origin()
def start_one_cv_reviewer():

    if request.method == 'POST':
        session['usage'], session['bool_chat'] = [], False
        initialize_api_type('One CV Reviewer')
        session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy('Payroll Expert')
        starting_prompt = gpt_engine.initialize_one_cv_reviewer()
        starting_prompt += '\n------\n' + session['job_vacancy']
        session['interview_transcript'] = [{"role": "user", 
                                            "content": starting_prompt},
                                        {"role" : "system", 
                                            "content" : "Halo, perkenalkan saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam mengevaluasi CV berdasarkan job vacancy yang ada. Saya akan memberikan penilaian berdasarkan total masa kerja relevan, skills, serta kelebihan dan kekurangan dari CV tersebut. Saya akan memberikan penilaian yang sejujur-jujurnya dengan mempertimbangkan semua aspek. Mari kita mulai."},
                                        ]
        
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt() 

    else:
        result = "Halo, perkenalkan saya adalah AI HR Assistant dari perusahaan Lawencon. Saya siap membantu Anda dalam mengevaluasi CV berdasarkan job vacancy yang ada. Saya akan memberikan penilaian berdasarkan total masa kerja relevan, skills, serta kelebihan dan kekurangan dari CV tersebut. Saya akan memberikan penilaian yang sejujur-jujurnya dengan mempertimbangkan semua aspek. Mari kita mulai."
    
    return jsonify({"next_question": result})

@app.route('/start_faq_functional_langchain', methods=['GET', 'POST'])
@cross_origin()
def start_faq_functional_langchain():
    if request.method == 'POST':
        session['interview_transcript'] = [{"role" : "system", 
                                        "content" : "Halo, perkenalkan saya adalah AI HR Assistant dari perusahaan Linov Roket Prestasi. Saya siap membantu Anda dalam pertanyaan terkait berbagai modul di web LinovHR! Ada yang bisa saya bantu?"},
                                        ]
        
        user_response = check_upload_file(request)
        result = gpt_engine.answer_faq_langchain(user_response, session)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        session['interview_transcript'].append({"role": "system", "content": result}) 

    else:
        session['usage'], session['bool_chat'] = [], True
        initialize_api_type('FAQ Functional Langchain')
        db = db_ops.langchain_connect_db()
        gpt_engine.initialize_faq_langchain(session, db)
        result = "Halo, perkenalkan saya adalah AI HR Assistant dari perusahaan Linov Roket Prestasi. Saya siap membantu Anda dalam pertanyaan terkait berbagai modul di web LinovHR! Ada yang bisa saya bantu?"
    
    return jsonify({"next_question": result})

@app.route('/start_faq_functional_assistant', methods=['GET', 'POST'])
@cross_origin()
def start_faq_functional_assistant():
    if request.method == 'POST':
        session['interview_transcript'] = [{"role" : "system", 
                                        "content" : "Halo, perkenalkan saya adalah AI HR Assistant dari perusahaan Linov Roket Prestasi. Saya siap membantu Anda dalam pertanyaan terkait berbagai modul di web LinovHR! Ada yang bisa saya bantu?"},
                                        ]
        
        user_response = check_upload_file(request)
        result = gpt_engine.answer_faq_assistant('post', thread=session['thread_assistant'], question=user_response)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        session['interview_transcript'].append({"role": "system", "content": result}) 

    else:
        session['usage'], session['bool_chat'] = [], True
        initialize_api_type('FAQ Functional Assistant')
        session['thread_assistant'] = gpt_engine.answer_faq_assistant('get')
        result = "Halo, perkenalkan saya adalah AI HR Assistant dari perusahaan Linov Roket Prestasi. Saya siap membantu Anda dalam pertanyaan terkait berbagai modul di web LinovHR! Ada yang bisa saya bantu?"
    
    return jsonify({"next_question": result})

@app.route('/start_faq_functional_cosine', methods=['GET', 'POST'])
@cross_origin()
def start_faq_functional_cosine():
    if request.method == 'POST':
        
        user_response = check_upload_file(request)
        session['interview_transcript'].append({"role": "user", "content": user_response})
        result = query_gpt()

        if '<--->' in result and 'Pertanyaan' in result:
            result = result.replace('<--->', '').replace('Pertanyaan :', '').strip()
            session['user_question'] = result
            result, session['list_cosine'], session['question_str'] = gpt_engine.faq_cosine_similarity(result)
            session['interview_transcript'].append({"role": "user", "content": result})
            result = query_gpt(result)
            result = query_gpt(result)

    else:
        session['usage'], session['bool_chat'] = [], True
        initialize_api_type('FAQ Functional Cosine')
        starting_prompt = gpt_engine.initialize_faq_cosine()
        session['interview_transcript'] = [{"role": "user", "content": starting_prompt}]
        result = query_gpt()
    
    return jsonify({"next_question": result})

@app.route('/chat_with_cs', methods=['POST'])
def chat_with_cs():
    # Logic to handle chat initiation
    # This could involve sending a message to a chat server or opening a new chat session.
    return jsonify({"message": "Chat with customer service started", "status": "success"})

@app.route('/tarik_kesimpulan', methods=['GET'])
@cross_origin()
def tarik_kesimpulan():
    session['interview_transcript'].append({"role": "user", "content": '--- WAKTU HABIS ---'})
    result = query_gpt()
    return jsonify({"next_question": result})

if __name__ == '__main__':
    app.run(debug=True)
    ### SEMENTARA, KALO TIPENYA CHAT, HRS GET DULU. KARENA BOT NYA HRS DULUAN NYAPA DAN NGASIH PERTANYAAN DULUAN
    ### KALO TIPE CHAT NYA FALSE, BISA LANGSUNG POST. KARENA CUMA LEMPAR CV DOANG
    ### KEDEPANNYA, TIPE NYA CHAT BISA POST LANGSUNG, TAPI YANG DI POST PERTAMA KALI ITU ADALAH PROMPT. TERGANTUNG FRONT END MAU GMN