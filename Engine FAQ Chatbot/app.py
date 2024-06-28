from flask import Flask, session, request, jsonify, render_template
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource, fields
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
import os, json, shutil, signal, sys, ast, re
from datetime import date, datetime, timedelta
from collections import OrderedDict
import uuid
from apscheduler.schedulers.background import BackgroundScheduler

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

# Dictionary to track last activity time for each session
last_activity_dict = {}

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
    session['gpt_api_type'] = api_type + '_' + str(session.sid) + '_' + current_time

def query_gpt(primary_key={}, additional_dict={}, one_time_message=''):
    answer, json_response = gpt_engine.hit_groq_api(session, one_time_message)
    session['history'].append({"role": "system", "content": answer})
    usage = json_response.get('usage', {})
    session['usage'].append(str(usage))
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

def check_inactive_sessions():
    current_time = datetime.now()
    inactive_sessions = []
    for sid, last_activity in list(last_activity_dict.items()):
        if current_time - last_activity > timedelta(minutes=5):
            inactive_sessions.append(sid)
    
    for sid in inactive_sessions:
        last_activity_dict.pop(sid, None)
        with app.app_context():
            session.pop(sid, None)

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_inactive_sessions, trigger="interval", minutes=1)
scheduler.start()

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    if file_required:
        parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

@namespace_ai_faq.route('/initialize_faq_chatbot')
class InitializeFaqChat(Resource):
    @cross_origin()
    def get(self):
        try:
            session['usage'], session['bool_chat'] = [], True
            initialize_api_type('FAQ Functional Cosine')
            starting_prompt = gpt_engine.initialize_faq_cosine()
            session['history'] = [{"role": "user", "content": starting_prompt}]
            id_chat = session['gpt_api_type']
            row_id, answer = query_gpt(primary_key={"id_chat": id_chat})
            last_activity_dict[id_chat] = datetime.now()
            return {'chat_id': id_chat, 'message': answer}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/faq_chatbot')
class FaqChatbot(Resource):
    parser = create_parser(False, user_answer={'type': str, 'required': True, 'help': 'Jawaban User Saat Chat', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            user_response = args['user_answer']
            id_chat = session['gpt_api_type']
            if id_chat not in last_activity_dict:
                return {'message': 'Session not found or has expired.'}, 400

            session['history'].append({"role": "user", "content": user_response})
            row_id, result = query_gpt(primary_key={"id_chat": id_chat})
            last_activity_dict[id_chat] = datetime.now()

            if '<--->' in result and 'Pertanyaan' in result:
                result = result.replace('<--->', '').replace('Pertanyaan :', '').strip()
                session['user_question'] = result
                result, session['list_cosine'], session['question_str'] = gpt_engine.faq_cosine_similarity(result)
                session['history'].append({"role": "user", "content": result})
                row_id, result = query_gpt(primary_key={"id_chat": id_chat}, one_time_message=result)
                row_id, result = query_gpt(primary_key={"id_chat": id_chat}, one_time_message=result)
            
            return {'chat_id': id_chat, 'message': result}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/faq_chatbot/<string:id_chat>')
class GetFaqChatbotChat(Resource):
    @cross_origin()
    def get(self, id_chat):
        try:
            result = db_ops.get_row_data({"id_chat": id_chat}, 'cosine_faq_functional', all_row=False)
            chat_history, pattern = [], r'---.*---'
            
            for i in ast.literal_eval(result['chat_history']):
                if '<--->' in i['content'] or bool(re.search(pattern, i['content'])):
                    continue
                elif 'format menjawab jika prompt bukan pertanyaan hris di linovhr' in i['content'].lower() and ' --- Jawaban mu ---' in i['content'].lower():
                    continue
                elif "dari kalimat berikut" in i['content'].lower() and "jawab '--- tidak ---'" in i['content'].lower():
                    continue
                else:
                    chat_history.append(i)

            return {'chat_history': chat_history}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/questions_list')
class QuestionsList(Resource):
    @cross_origin()
    def get(self):
        try:
            gpt_engine.initialize_faq_cosine()
            questions = gpt_engine.faq_questions.values.tolist()
            return {'questions': questions}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

##### ===================== FAQ MANUAL CHAT ===================== #####

@namespace_manual_faq.route('/initialize_faq_manual')
class InitializeFaqManual(Resource):
    
    parser = reqparse.RequestParser().add_argument('question_context', type=str,required=True, help='Please insert question context', location='form')
    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            question_context = args['question_context']
            
            # Inisialisasi variabel sesi untuk chat
            session['usage'], session['bool_chat'], session['history'] = [], True, []

            # Menggenerate id_chat yang unik menggunakan UUID
            id_chat = str(uuid.uuid4())
            session['id_chat'] = id_chat  # Menyimpan id_chat ke dalam session
            
            # Mengatur tipe API untuk chat yang sesuai
            initialize_api_type('FAQ Chat Room')
            
            # create room di db
            db_ops.create_room_chat('FAQ Chat Room', id_chat, question_context)
            
            # Mengembalikan response dengan id_chat yang baru digenerate
            last_activity_dict[id_chat] = datetime.now()
            return {'chat_id': id_chat, 'message': 'Terima Kasih atas pesan anda. Mohon menunggu untuk sementara waktu. Tiket anda sedang dalam proses penugasan ke tim Customer Service kami.'}, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

def create_parser():
    parser = reqparse.RequestParser()
    parser.add_argument('room_chat', type=str, required=True, help='ID Room Chat is required', location='form')
    parser.add_argument('role', type=str, required=True, help='Role must be either user or functional', location='form', choices=('user', 'functional'))
    parser.add_argument('user_id', type=str, required=True, help='User Id is required', location='form')
    parser.add_argument('message', type=str, required=True, help='Message is required', location='form')
    return parser

@namespace_manual_faq.route('/faq_manual/chat', methods=['POST'])
class FAQChat(Resource):
    parser = create_parser()

    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            room_chat = args['room_chat']
            if room_chat not in last_activity_dict:
                return {'message': 'Session not found or has expired.'}, 400

            role = args['role']
            user_id = args['user_id']
            message = args['message']

            insert_to_db = db_ops.upsert_manual_chat('FAQ Chat Room', room_chat, message, role, user_id)
            print(insert_to_db)

            if isinstance(insert_to_db, str) and "Success" in insert_to_db:
                last_activity_dict[room_chat] = datetime.now()
                return {'room_chat': room_chat, 'message': message, 'status': 'Success'}, 200
            else:
                return {'message': 'Room ID not found in the database'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_manual_faq.route('/faq_manual/end_session/<string:id_chat>')
class EndFaqManualSession(Resource):
    @cross_origin()
    def get(self, id_chat):
        try:
            # Clear the session data for the given chat ID
            last_activity_dict.pop(id_chat, None)
            with app.app_context():
                if 'id_chat' in session and session['id_chat'] == id_chat:
                    session.clear()
            return {'message': 'Session ended successfully.'}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_manual_faq.route('/faq_manual/<string:room_id>')
class GetFaqManualChat(Resource):
    @cross_origin()
    def get(self, room_id):
        try:
            # Using id_chat to fetch data
            result = db_ops.get_row_data({"room_id": room_id}, 'faq_manual_chat', all_row=False)
            if result and 'chat_transcripts' in result:
                transcripts = result['chat_transcripts']
                question_context = result.get('question_context', 'No context available')
                sorted_transcripts = {k: transcripts[k] for k in sorted(transcripts)}
                response = {
                    "room_id": room_id,
                    "question_context": question_context,
                    "chat_transcripts": sorted_transcripts
                }
                return jsonify(response), 200
            else:
                return jsonify({"message": "Chat history not found"}), 404
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 400

@namespace_manual_faq.route('/faq_manual/get_knowledge/<string:id_chat>')
class GetFaqManualChatKnowledge(Resource):
    @cross_origin()
    def get(self, id_chat):
        try:
            session['usage'], session['bool_chat'], session['history'] = [], True, []
            initialize_api_type('Manual Chat Knowledge')
            
            result = db_ops.get_row_data({"room_id": id_chat}, 'faq_manual_chat', all_row=False)
            
            # Log the retrieved result for debugging
            print(f"Retrieved result for id_chat {id_chat}: {result}")

            if not result or 'chat_transcripts' not in result:
                return {'message': 'Chat transcripts not found or incomplete'}, 404

            chat_transcripts = result['chat_transcripts']
            sorted_chat_transcripts = dict(OrderedDict(sorted(chat_transcripts.items())))

            gpt_engine.initialize_faq_cosine()
            prompt_knowledge = gpt_engine.faq_chat_manual.replace('<<< Transkrip >>>', str(sorted_chat_transcripts))
            
            # Capture the response from query_gpt function
            response = query_gpt(primary_key={"id_chat": id_chat}, one_time_message=prompt_knowledge)
            print(f"query_gpt response: {response}")

            # Handle the response appropriately
            if len(response) == 2:
                row_id, answer = response
                return {'chat_id': id_chat, 'message': answer}, 200
            else:
                return {'message': 'Unexpected response from query_gpt'}, 500
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5001)