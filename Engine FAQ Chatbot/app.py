from flask import Flask, session, request, jsonify, render_template
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource, fields
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
import os, json, shutil, signal, sys, ast, re
from datetime import date, datetime
from collections import OrderedDict
import uuid

module_dir = 'modules\\'
modules_path = ['db', 'file_processor', 'gpt']
for mp in modules_path:
    mp = 'modules\\' + mp + '_module\\' 
    if mp not in sys.path:
        sys.path.append(mp)

from db_manager import DatabaseOperations
from file_manager import FileHandler
from gpt_manager import GPTEngine

db_ops = DatabaseOperations()
file_handler = FileHandler()
gpt_engine = GPTEngine()

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
cors = CORS(app)

api = Api(app, version='1.0', title='FAQ Chatbot Functional',
        description='Dokumentasi API FAQ Chatbot Functional')
namespace_ai_faq = api.namespace('Chat With AI', description='API untuk chat bersama AI FAQ Chatbot')
namespace_manual_faq = api.namespace('Chat with Functional Team', description='API untuk chat manual bersama tim Functional')

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
    session['gpt_api_type'] =  api_type + '_' + str(session.sid) + '_' +  current_time

def query_gpt(primary_key={}, additional_dict={}, one_time_message=''):
    # return 'Dummy Response', {'message' : 'Dummy Response'}
    
    # answer, json_response = gpt_engine.hit_gpt_api(session, one_time_message)
    answer, json_response = gpt_engine.hit_groq_api(session, one_time_message)

    ## ====
    session['history'].append({"role": "system", "content": answer})
    usage = json_response.get('usage', {})
    session['usage'].append(str(usage)) 
    ## ====
    
    log_file_content = file_handler.save_chat_transcript(session)
    dict_form, answer = gpt_engine.format_response_gpt(session, answer)
    dict_form = {**additional_dict, **dict_form}
    row_id = db_ops.store_to_db(session['gpt_api_type'].split('_')[0], 
                                session['bool_chat'], 
                                session['gpt_api_type'], 
                                log_file_content, 
                                dict_data=dict_form,
                                id_dict=primary_key)

    return row_id, answer

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    if file_required:
        parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

@namespace_manual_faq.route('/initialize_faq_manual')
class initialize_faq_manual(Resource):
    @cross_origin()
    def get(self):
        try:
            # Inisialisasi variabel sesi untuk chat
            session['usage'], session['bool_chat'], session['history'] = [], True, []

            # Menggenerate id_chat yang unik menggunakan UUID
            id_chat = str(uuid.uuid4())
            session['id_chat'] = id_chat  # Menyimpan id_chat ke dalam session

            # Mengatur tipe API untuk chat yang sesuai
            initialize_api_type('FAQ Manual Chat')
            
            # Mengembalikan response dengan id_chat yang baru digenerate
            return {'chat_id': id_chat, 'message': 'Chat With Functional Team Has Started.'}, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/faq_chatbot')
class faq_chatbot(Resource):
    parser = create_parser(False, 
                            user_answer={'type': str, 'required': True, 'help': 'Jawaban User Saat Chat', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            user_response = args['user_answer']
            id_chat = session['gpt_api_type']
            session['history'].append({"role": "user", "content": user_response})
            row_id, result = query_gpt(primary_key={"id_chat" : id_chat})

            if '<--->' in result and 'Pertanyaan' in result:
                result = result.replace('<--->', '').replace('Pertanyaan :', '').strip()
                session['user_question'] = result
                result, session['list_cosine'], session['question_str'] = gpt_engine.faq_cosine_similarity(result)
                session['history'].append({"role": "user", "content": result})
                row_id, result = query_gpt(primary_key={"id_chat" : id_chat}, one_time_message=result)
                row_id, result = query_gpt(primary_key={"id_chat" : id_chat}, one_time_message=result)
            
            return {'chat_id' : id_chat, 'message': result}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/faq_chatbot/<string:id_chat>')
class get_faq_chatbot_chat(Resource):
    @cross_origin()

    def get(self, id_chat):

        try:
            result = db_ops.get_row_data({"id_chat" : id_chat}, 'cosine_faq_functional', all_row=False)
            chat_history, pattern = [], r'---.*---'
            
            for i in ast.literal_eval(result['chat_history']):
                
                
                if '<--->' in i['content'] or bool(re.search(pattern, i['content'])):
                    continue
                    
                elif 'format menjawab jika prompt bukan pertanyaan hris di linovhr' in i['content'].lower() and ' --- Jawaban mu ---' in i['content'].lower() :
                    continue

                elif "dari kalimat berikut" in i['content'].lower() and "jawab '--- tidak ---'" in i['content'].lower():
                    continue

                else:
                    chat_history.append(i)

            return {'chat_history' : chat_history}, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/questions_list')
class questions_list(Resource):
    @cross_origin()
    def get(self):

        try:
            gpt_engine.initialize_faq_cosine()
            questions = gpt_engine.faq_questions.values.tolist()
            return {'questions' : questions}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

##### ===================== FAQ MANUAL CHAT ===================== #####

@namespace_manual_faq.route('/initialize_faq_manual')
class initialize_faq_manual(Resource):
    
    @cross_origin()
    def get(self):
        try:
            session['usage'], session['bool_chat'],session['history'] = [], True, []
            initialize_api_type('FAQ Manual Chat')
            id_chat = session['gpt_api_type']
            return {'chat_id' : id_chat, 'message': 'Chat With Functional Team Has Started.'}, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

def create_parser():
    parser = reqparse.RequestParser()
    parser.add_argument('id_chat', type=str, required=True, help='ID Chat is required', location='form')
    parser.add_argument('message', type=str, required=True, help='Message is required', location='form')
    parser.add_argument('role', type=str, required=True, help='Role must be either user or functional', location='form', choices=('user', 'functional'))
    return parser

@namespace_manual_faq.route('/faq_manual/chat', methods=['POST'])
class FAQChat(Resource):
    parser = create_parser()

    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            id_chat = args['id_chat']
            message = args['message']
            role = args['role']

            db_ops.upsert_manual_chat('FAQ Manual Chat', id_chat, message, role)
            return {'chat_id': id_chat, 'message': message, 'status': 'Success'}, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_manual_faq.route('/faq_manual/<string:id_chat>')
class get_faq_manual_chat(Resource):
    @cross_origin()
    def get(self, id_chat):
        try:
            # Using id_chat to fetch data
            result = db_ops.get_row_data({"id_chat": id_chat}, 'faq_manual_chat', all_row=False)
            if result and 'chat_transcripts' in result:
                transcripts = result['chat_transcripts']
                sorted_transcripts = {k: transcripts[k] for k in sorted(transcripts)}
                return sorted_transcripts, 200
            else:
                return {'message': "Chat history not found"}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

# @namespace_manual_faq.route('/faq_manual/get_knowledge/<string:id_chat>')
# class get_faq_manual_chat_knowledge(Resource):
#     @cross_origin()
#     def get(self, id_chat):

#         try:
#             session['usage'], session['bool_chat'], session['history'] = [], True, []
#             initialize_api_type('Manual Chat Knowledge')
        
#             result = db_ops.get_row_data({"id_chat" : id_chat}, 'faq_manual_chat', all_row=False)
#             chat_transcript_user, faq_chat_functional = result['chat_transcript_user'], result['chat_transcript_functional']
#             all_chat = {**chat_transcript_user, **faq_chat_functional}
#             sorted_all_chat = dict(OrderedDict(sorted(all_chat.items())))

#             gpt_engine.initialize_faq_cosine()
#             prompt_knowledge = gpt_engine.faq_chat_manual.replace('<<< Transkrip >>>', str(sorted_all_chat))
#             row_id, answer = query_gpt(primary_key={"id_chat" : id_chat}, one_time_message=prompt_knowledge)
            
#             return answer
        
#         except Exception as e:
#             print(e)
#             return {'message': str(e)}, 400
        
if __name__ == '__main__':
    app.run(debug=True, port=5001)