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
import nltk
import base64

module_dir = 'modules/'
modules_path = ['db', 'file_processor', 'gpt']
for mp in modules_path:
    mp = 'modules/' + mp + '_module/'
    if mp not in sys.path:
        sys.path.append(mp)

from modules.db_module.db_manager import DatabaseOperations
from modules.file_processor_module.file_manager import FileHandler
from modules.gpt_module.gpt_manager import GPTEngine

db_ops = DatabaseOperations()
file_handler = FileHandler()
gpt_engine = GPTEngine()

current_dir = os.getcwd()

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = current_dir + "/flask_session"
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
    
    session_id = session.sid
    session['session_id'] = session_id
    
def initialize_session_chat(room_id):
    session_id = session.sid
    session[room_id] = 'chat_session_' + session_id
    
available_modules = [
    "Workbench", "Time & Attendances", "Recruitment", "Reimbursement", 
    "Loan", "Payroll", "Organization", "Competency", 
    "Performances", "Career Path", "Learning Management System"
]

def is_module_available(module_name):
    return module_name in available_modules

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

def get_module_from_question(question):
    # Logika sederhana untuk mengekstrak nama modul dari pertanyaan
    for module in available_modules:
        if module.lower() in question.lower():
            return module
    return None

# for reading config files
def read_config_file(file_name):
    with open(file_name) as f:
        data = json.load(f)
    return data

# for chat config
config_chat = read_config_file('config_chat.json')

def check_inactive_sessions():
    try:
        current_time = datetime.now()
        inactive_sessions = []
        for sid, last_activity in list(last_activity_dict.items()):
            if current_time - last_activity > timedelta(minutes=config_chat["minutes"]):
                inactive_sessions.append(sid)
        
        for sid in inactive_sessions:
            last_activity_dict.pop(sid, None)
            if sid:
                current_status = 'Ended'
                db_ops.update_end_chat('FAQ Chat Room', sid, current_status)
                message = "Your chat session has been closed due to inactivity."
                db_ops.upsert_manual_chat('FAQ Chat Room', sid, message, 'system')
                print(f"Notifikasi auto close chat untuk room_id: {sid}")

    except Exception as e:
        print(e)


scheduler = BackgroundScheduler()
scheduler.add_job(func=check_inactive_sessions, trigger="interval", minutes=config_chat["minutes"])
scheduler.start()

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

@namespace_ai_faq.route('/initialize_faq_chatbot')
class InitializeFaqChat(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('user_id', type=str, required=True, help='User ID is required', location='form')

    @namespace_ai_faq.expect(parser)
    @cross_origin()
    def post(self):
        args = self.parser.parse_args()
        user_id = args['user_id']
        
        try:
            session['usage'], session['bool_chat'] = [], True
            initialize_api_type('FAQ Functional Cosine')
            starting_prompt = gpt_engine.initialize_faq_cosine()
            session['history'] = [{"role": "user", "content": starting_prompt}]
            
            room_id = str(uuid.uuid4())
            session['room_id'] = room_id
            
            row_id, answer = query_gpt(primary_key={"room_id": room_id}, additional_dict={"user_id": user_id})
            last_activity_dict[room_id] = datetime.now()
            
            print(user_id)
            
            return {'room_id': room_id, 'message': answer}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/faq_chatbot')
class FaqChatbot(Resource):
    parser = create_parser(False, user_answer={'type': str, 'required': True, 'help': 'Jawaban User Saat Chat', 'location': 'form'},
                           user_modules={'type': str, 'required': True, 'help': 'modules yang disubscribe user contoh: payroll, workbench', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            user_response = args['user_answer']
            
            if args['user_modules']:
                formatted_string = ', '.join(part.strip() for part in args['user_modules'].split(','))
                list_of_modules = [part.strip() for part in formatted_string.split(',')]
            else:
                list_of_modules = []
            
            if 'session_id' not in session:
                return {'message': 'Session not found or has expired.'}, 400
            
            room_id = session['room_id']
            
            # Save the user response to the database
            db_ops.upsert_manual_chat('FAQ Functional Cosine', room_id, user_response, 'user')

            session['history'].append({"role": "user", "content": user_response})
            row_id, result = query_gpt(primary_key={"room_id": room_id})
            if row_id is None:  # Modul tidak tersedia
                return {'room_id': room_id, 'message': result}, 200
            
            last_activity_dict[room_id] = datetime.now()

            ai_response = ''
            
            if '<--->' in result and 'Pertanyaan' in result:
                result = result.replace('<--->', '').replace('Pertanyaan :', '').strip()
                session['user_question'] = result
                result, session['list_cosine'], session['question_str'] = gpt_engine.faq_cosine_similarity(result)
                session['history'].append({"role": "user", "content": result})
                row_id, result = query_gpt(primary_key={"room_id": room_id}, one_time_message=result)
                
                row_id, result = query_gpt(primary_key={"room_id": room_id}, one_time_message=result)
                
                # Check if the question is related to an unavailable module
                answered_module = session['list_cosine'][0]['module'].lower()
                
                
                if answered_module not in list_of_modules:
                    message = f'Maaf, modul {answered_module} belum tersedia bagi perusahaan Anda. Silahkan hubungi tim Linov untuk informasi lebih lanjut.'
                    
                    db_ops.upsert_manual_chat('FAQ Functional Cosine', room_id, message, 'system')
                    
                    return {'room_id': room_id, 'message': message}, 200
                else:
                    db_ops.upsert_manual_chat('FAQ Functional Cosine', room_id, result, 'system')
            
            return {'room_id': room_id, 'message': result}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/faq_chatbot/<string:room_id>')
class GetFaqChatbotChat(Resource):
    @cross_origin()
    def get(self, room_id):
        try:
            result = db_ops.get_row_data({"room_id": room_id}, 'cosine_faq_functional', all_row=False)
            
            result = result['chat_transcripts']

            return result, 200
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

@namespace_ai_faq.route('/faq_chatbot/end_session/<string:room_id>')
class EndFaqManualSession(Resource):
    @cross_origin()
    def get(self, room_id):
        try:
            # Clear the session data for the given chat ID
            last_activity_dict.pop(room_id, None)
            with app.app_context():
                if 'room_id' in session and session['room_id'] == room_id:
                    session.clear()
            return {'message': 'Session ended successfully.'}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@namespace_ai_faq.route('/modules_list')
class ModulesList(Resource):
    modules = [
        "Workbench", "Time & Attendances", "Recruitment", "Reimbursement", 
        "Loan", "Payroll", "Organization", "Competency", 
        "Performances", "Career Path", "Learning Management System"
    ]

    @cross_origin()
    def get(self):
        return jsonify(self.modules)
        
@namespace_ai_faq.route('/get_questions_by_module')
class GetQuestionsByModule(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('module', type=str, required=True, help='Please provide a module name to filter questions', location='args')

    @namespace_manual_faq.expect(parser)
    @cross_origin()
    def get(self):
        args = self.parser.parse_args()
        module = args['module']
        try:
            result = db_ops.get_questions_by_module(module)
            if result:
                return jsonify(result), 200
            else:
                return jsonify({"message": "No records found"}), 404
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 500
        
@namespace_ai_faq.route('/faqs')
class FAQs(Resource):
    @cross_origin()
    def get(self):
        try:
            faqs = db_ops.get_faqs()
            if isinstance(faqs, dict) and 'error' in faqs:
                return {'message': faqs['error']}, 500
            return jsonify(faqs), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@namespace_ai_faq.route('/random_questions')
class RandomQuestions(Resource):
    @cross_origin()
    def get(self):
        try:
            random_questions = db_ops.get_random_questions()
            if isinstance(random_questions, dict) and 'error' in random_questions:
                return {'message': random_questions['error']}, 500
            return jsonify(random_questions), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@namespace_ai_faq.route('/update_rating')
class UpdateRating(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('question', type=str, required=True, help='Masukan List Question dari Excel FAQ', location='form')
    parser.add_argument('rating_change', type=str, required=True, help='Rating change must be either good or bad', choices=('Good', 'Bad'), location='form')

    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            question = args['question']
            rating_change_str = args['rating_change']

            # Convert rating_change from string to integer
            if rating_change_str == 'Good':
                rating_change = 1
            elif rating_change_str == 'Bad':
                rating_change = -1

            # Initialize cosine similarity check
            gpt_engine.initialize_faq_cosine()
            result, list_cosine, question_str = gpt_engine.faq_cosine_similarity(question)

            # Ensure list_cosine is not empty and has similarity scores
            if not list_cosine or 'similarity_score' not in list_cosine[0]:
                return {'message': 'Pertanyaan tidak sesuai dengan FAQ yang tersedia.'}, 400

            # Check if the highest similarity score is below threshold
            similarity_score = list_cosine[0]['similarity_score']
            if similarity_score < 0.8:
                return {'message': 'Pertanyaan tidak sesuai dengan FAQ yang tersedia.'}, 400

            faq_question = list_cosine[0]['question']

            result = db_ops.update_question_rating(faq_question, rating_change)
            if 'error' in result:
                return {'message': result['error']}, 500

            return {'message': result['message']}, 200

        except Exception as e:
            return {'message': str(e)}, 400

@namespace_ai_faq.route('/popular_questions_by_module')
class PopularQuestionsByModule(Resource):
    @cross_origin()
    def get(self):
        try:
            popular_questions = db_ops.get_popular_questions_by_module()
            if isinstance(popular_questions, dict) and 'error' in popular_questions:
                return {'message': popular_questions['error']}, 500
            return jsonify(popular_questions), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@namespace_ai_faq.route('/popular_questions')
class PopularQuestions(Resource):
    @cross_origin()
    def get(self):
        try:
            popular_questions = db_ops.get_popular_questions_sorted_by_rating()
            if isinstance(popular_questions, dict) and 'error' in popular_questions:
                return {'message': popular_questions['error']}, 500
            return jsonify(popular_questions), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@namespace_ai_faq.route('/list_chats_by_user_id')
class ChatsBySection(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('user_id', type=str, required=False, help='Please provide a user_id', location='args')
    parser.add_argument('page', type=int, required=False, default=1, help='Page number', location='args')
    parser.add_argument('limit', type=int, required=False, default=10, help='Number of chats per page', location='args')

    @namespace_ai_faq.expect(parser)
    @cross_origin()
    def get(self):
        args = self.parser.parse_args()
        user_id = args.get('user_id', None)
        page = args.get('page', 1)
        limit = args.get('limit', 10)
        skip = (page - 1) * limit

        try:
            collection = db_ops.db_ai_mongo['cosine_faq_functional']

            # Query untuk mendapatkan chat berdasarkan user_id dengan pagination
            chats = collection.find({"user_id": user_id}).sort("last_updated", -1).skip(skip).limit(limit)
            chat_list = []
            for chat in chats:
                chat['_id'] = str(chat['_id'])  # Convert ObjectId to string
                chat.pop('chat_history', None)
                chat_list.append(chat)
                
            return jsonify(chat_list), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
##### ========================================= FAQ MANUAL CHAT ========================================= #####

@namespace_manual_faq.route('/initialize_faq_manual')
class InitializeFaqManual(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('question_context', type=str, required=True, help='Please insert question context', location='form')
    parser.add_argument('user_id', type=str, required=True, help='Insert User Id (diambil dari data login)', location='form')
    parser.add_argument('user_name', type=str, required=True, help='Insert User Name (diambil dari data login)', location='form')
    parser.add_argument('user_avatar', type=FileStorage, required=True, help='Upload User Avatar in JPG/JPEG/PNG', location='files')
    parser.add_argument('tenant_name', type=str, required=True, help='Insert Tenant Name', location='form')
    parser.add_argument('platform', type=str, required=True, help='Insert Platform Name', location='form')

    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            question_context = args['question_context']
            user_id = args['user_id']
            user_name = args['user_name']
            avatar = args['user_avatar']
            tenant_name = args['tenant_name']
            platform = args['platform']
            
            # Konversi avatar ke base64
            user_avatar = base64.b64encode(avatar.read()).decode('utf-8')
            
            session['usage'], session['bool_chat'], session['history'] = [], True, []
            room_id = str(uuid.uuid4())
            initialize_api_type('FAQ Chat Room')
            status = "Waiting"
            functional_id = "-"
            functional_avatar = "-"
            
            db_ops.create_room_chat('FAQ Chat Room', room_id, question_context, user_id, status, functional_id, user_name, user_avatar, tenant_name, platform, functional_avatar)
            
            return {'room_id': room_id, 'question_context': question_context, 'user_id': user_id, 'user_name': user_name, 'user_avatar': user_avatar, 'tenant_name': tenant_name, 'platform': platform, 'message': 'Terima Kasih atas pesan anda. Mohon menunggu untuk sementara waktu'}, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_manual_faq.route('/start_chat')
class StartChat(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('room_id', type=str, required=True, help='Please insert room id', location='form')
    parser.add_argument('functional_id', type=str, required=True, help='Insert Current cs that handle the user (diambil dari data login)', location='form')
    parser.add_argument('functional_avatar', type=FileStorage, required=True, help='Upload functional Avatar in JPG/JPEG/PNG', location='files')

    @api.expect(parser)
    @cross_origin()
    def patch(self):
        try:
            args = self.parser.parse_args()
            room_id = args['room_id']
            functional_id = args['functional_id']
            current_status = "On Going"
            avatar = args['functional_avatar']
            functional_avatar = base64.b64encode(avatar.read()).decode('utf-8')
            initialize_api_type('FAQ Chat Room')
            initialize_session_chat(room_id)
            last_activity_dict[room_id] = datetime.now()
            update_status_result = db_ops.update_chat_status('FAQ Chat Room', room_id, current_status, functional_id, functional_avatar)
            if update_status_result:
                chat_data = db_ops.get_row_data({"room_id": room_id}, 'faq_manual_chat', all_row=False)
                return {
                    'message': 'Tim Customer Service Telah Terhubung',
                    'status': current_status,
                    'user_avatar': chat_data.get('user_avatar'),
                    'tenant_name': chat_data.get('tenant_name'),
                    'platform': chat_data.get('platform'),
                    'functional_avatar': chat_data.get('functional_avatar')
                }, 200
            else:
                return {'message': 'Failed to start chat. Room ID not found.'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

def create_parser():
    parser = reqparse.RequestParser()
    parser.add_argument('room_chat', type=str, required=True, help='ID Room Chat is required', location='form')
    parser.add_argument('role', type=str, required=True, help='Role must be either user or functional', location='form', choices=('user', 'functional'))
    parser.add_argument('message', type=str, required=True, help='Message is required', location='form')
    return parser

@namespace_manual_faq.route('/faq_manual/chat', methods=['POST'])
class FAQChat(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('room_chat', type=str, required=True, help='ID Room Chat is required', location='form')
    parser.add_argument('role', type=str, required=True, help='Role must be either user or functional', location='form', choices=('user', 'functional'))
    parser.add_argument('message', type=str, required=True, help='Message is required', location='form')

    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            room_chat = args['room_chat']
            role = args['role']
            message = args['message']
            
            result = db_ops.get_row_data({"room_id": room_chat}, 'faq_manual_chat', all_row=False)
            # if result['status'] == 'On Going':
            insert_to_db = db_ops.upsert_manual_chat('FAQ Chat Room', room_chat, message, role)
            if result['status'] == 'On Going' and isinstance(insert_to_db, str) and "Success" in insert_to_db:
                last_activity_dict[room_chat] = datetime.now()
                chat_data = db_ops.get_row_data({"room_id": room_chat}, 'faq_manual_chat', all_row=False)
                return {
                    'room_chat': room_chat,
                    'message': message,
                    'status': 'Success',
                    'user_avatar': chat_data.get('user_avatar'),
                    'tenant_name': chat_data.get('tenant_name'),
                    'platform': chat_data.get('platform')
                }, 200
            else:
                return {'message': 'Session not found or has expired.'}, 404
            # else:
            #     return {'message': 'Room ID not found in the database'}, 404
                
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_manual_faq.route('/faq_manual/end_session/<string:room_id>')
class EndFaqManualSession(Resource):
    @cross_origin()
    def get(self, room_id):
        try:
            
            current_status = "Ended"
            # Update the chat status to 'ended'
            initialize_api_type('FAQ Chat Room')
            update_status_result = db_ops.update_end_chat('FAQ Chat Room', room_id, current_status)
            current_datetime = datetime.now()
            if update_status_result:
                
                # last_activity_dict.pop(room_id, None)
                with app.app_context():
                    if room_id in last_activity_dict:
                        last_activity_dict.pop(room_id, None)
                    # if room_id in session:
                    #     session.clear()
                return {'message': f'Chat Session with the following customer has ended \n{current_datetime}', 'status': current_status}, 200
            else:
                return {'message': 'Room ID not found.'}, 404
            
            # return {'message': 'Session ended successfully.'}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@namespace_manual_faq.route('/faq_manual/<string:room_id>')
class GetFaqManualChat(Resource):
    @cross_origin()
    def get(self, room_id):
        try:
            result = db_ops.get_row_data({"room_id": room_id}, 'faq_manual_chat', all_row=False)
            if result and 'chat_transcripts' in result:
                transcripts = result['chat_transcripts']
                question_context = result.get('question_context', 'No context available')
                sorted_transcripts = {k: transcripts[k] for k in sorted(transcripts)}
                response = {
                    "room_id": room_id,
                    "question_context": question_context,
                    "chat_transcripts": sorted_transcripts,
                    "user_avatar": result.get('user_avatar'),
                    "tenant_name": result.get('tenant_name'),
                    "platform": result.get('platform')
                }
                return jsonify(response), 200
            else:
                return jsonify({"message": "Chat history not found"}), 404
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 400

@namespace_manual_faq.route('/faq_manual/get_knowledge/<string:room_id>')
class GetFaqManualChatKnowledge(Resource):
    @cross_origin()
    def get(self, room_id):
        try:
            session['usage'], session['bool_chat'], session['history'] = [], True, []
            initialize_api_type('Manual Chat Knowledge')
            
            result = db_ops.get_row_data({"room_id": room_id}, 'faq_manual_chat', all_row=False)
            
            # Log the retrieved result for debugging
            # print(f"Retrieved result for room_id {room_id}: {result}")

            if not result or 'chat_transcripts' not in result:
                return {'message': 'Chat transcripts not found or incomplete'}, 404

            chat_transcripts = result['chat_transcripts']
            # sorted_chat_transcripts = dict(OrderedDict(sorted(chat_transcripts.items())))

            gpt_engine.initialize_faq_cosine()
            prompt_knowledge = gpt_engine.faq_chat_manual.replace('<<< Transkrip >>>', str(chat_transcripts))
            
            # Capture the response from query_gpt function
            response = query_gpt(primary_key={"room_id": room_id}, one_time_message=prompt_knowledge)
            # print(f"query_gpt response: {response}")
            
            

            # Handle the response appropriately
            if len(response) == 2:
                row_id, answer = response
                return {'room_id': room_id, 'message': answer}, 200
            else:
                return {'message': 'Unexpected response from query_gpt'}, 500
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

# ######### GET ALL CHAT USERS
@namespace_manual_faq.route('/faq_manual/list_chat_rooms')
class GetFaqListChat(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('functional_id', type=str, required=True, help='ID Functional is required', location='args')
    
    @api.expect(parser)
    @cross_origin()
    def get(self):
        try:
            initialize_api_type('FAQ Chat Room')
            
            # Ambil parameter query functional_id
            args = self.parser.parse_args()
            functional_id = args.get('functional_id')
            
            # Panggil fungsi dengan parameter sorting
            result = db_ops.get_all_chats(functional_id=functional_id)
            
            if isinstance(result, dict) and 'error' in result:
                return jsonify({"message": result['error']}), 500
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 400

########## Filter by status
@namespace_manual_faq.route('/filter_by_status')
class FilterByStatus(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('status_chat', type=str, required=True, help='Choose status to be filtered', location='args', choices=('Waiting', 'On Going', 'Ended'))

    @namespace_manual_faq.expect(parser)
    @cross_origin()
    def get(self):
        args = self.parser.parse_args()
        status = args['status_chat']
        try:
            chats = db_ops.filter_by_status(status)
            return jsonify(chats), 200
        except Exception as e:
            return jsonify({'message': f"An error occurred: {str(e)}"}), 500

################# Search By Name

@namespace_manual_faq.route('/search_by_name')
class SearchByName(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, required=True, help='Please provide a name to search for', location='args')

    @namespace_manual_faq.expect(parser)
    @cross_origin()
    def get(self):
        args = self.parser.parse_args()
        user_name = args['name']
        try:
            result = db_ops.search_by_name(user_name)
            if result:
                return jsonify(result), 200
            else:
                return jsonify({"message": "No records found"}), 404
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 500

# ################ user give feedback to functional
@namespace_manual_faq.route('/feedback_to_functional')
class functionalsFeedback(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('functional_id', type=str, required=True, help='Please provide functional id', location='args')
    parser.add_argument('room_id', type=str, required=True, help='Please provide the room_id', location='args')
    parser.add_argument('rate', type=int, required=True, help='Please rate the functional response', location='args')
    parser.add_argument('description', type=str, required=True, help='Please describe your experience with this functional', location='args')

    @namespace_manual_faq.expect(parser)
    @cross_origin()
    def post(self):
        args = self.parser.parse_args()
        functional = args['functional_id']
        room_id = args['room_id']
        rate = args['rate']
        description = args['description']
        
        try:
            result = db_ops.RateFuntional("FAQ FUNCTIONALs FEEDBACK", functional, room_id, rate, description)
            
            if result == "Success":
                return jsonify({"message": "Feedback-mu telah direkam. Terima kasih!"}), 200
            else:
                return jsonify({"message": "No records found"}), 404
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 500
        
##### GET Feedback For Functional
@namespace_manual_faq.route('/feedbacks_to_functional')
class FeedbacksForFunctional(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('functional_id', type=str, required=True, help='Please provide functional id', location='args')

    @namespace_manual_faq.expect(parser)
    @cross_origin()
    def get(self):
        args = self.parser.parse_args()
        functional_id = args['functional_id']
        try:
            feedbacks = db_ops.get_feedback_for_functional(functional_id)
            if 'error' in feedbacks:
                return jsonify({"message": feedbacks['error']}), 500
            return jsonify(feedbacks), 200
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 500
        
@namespace_manual_faq.route('/sentiment_analysis')
class SentimentAnalysis(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('functional_id', type=str, required=True, help='Please provide functional id', location='form')

    @namespace_manual_faq.expect(parser)
    @cross_origin()
    def post(self):
        args = self.parser.parse_args()
        functional_id = args['functional_id']

        try:
            feedbacks = db_ops.get_feedback_for_functional(functional_id)
            if 'error' in feedbacks:
                return jsonify({"message": feedbacks['error']}), 500

            results = []
            for feedback in feedbacks:
                description = feedback['description']
                rate = feedback['rate']
                results.append({"rate": rate, "description": description})
            
            starting_prompt = gpt_engine.intialize_sentiment_analysis(f"{results}")
            
            session['history'] = [{"role": "user", "content": starting_prompt}]
            
            answer, json_response = gpt_engine.hit_groq_api(session, one_time_message='')
            
            print(answer)            
            
            dict_form = gpt_engine.format_sentiment_analysis(answer)
            
            store_result = db_ops.store_sentiment_analysis_result(functional_id, dict_form)
            if store_result != "Success":
                return jsonify({"message": store_result}), 500
            
            return dict_form, 200
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 500
        
@namespace_manual_faq.route('/sentiment_analysis/all')
class GetAllSentimentAnalysis(Resource):
    @cross_origin()
    def get(self):
        try:
            # Retrieve all documents from the sentiment_analysis collection
            results = db_ops.get_row_data({}, 'sentiment_analysis', all_row=True)
            if isinstance(results, list):
                # Convert ObjectId to string for each document
                for doc in results:
                    doc['_id'] = str(doc['_id'])
                return jsonify(results), 200
            else:
                return {'message': 'No records found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 500
        
@namespace_manual_faq.route('/sentiment_analysis/<string:functional_id>')
class GetSentimentAnalysisByFunctionalId(Resource):
    @cross_origin()
    def get(self, functional_id):
        try:
            # Retrieve documents for a specific functional_id from the sentiment_analysis collection
            result = db_ops.get_row_data({"functional_id": functional_id}, 'sentiment_analysis', all_row=False)
            if result:
                result['_id'] = str(result['_id'])  # Convert ObjectId to string
                return jsonify(result), 200
            else:
                return {'message': 'No records found for the given functional_id'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 500
        
@namespace_manual_faq.route('/evaluate_question')
class EvaluateQuestion(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('room_id', type=str, required=True, help='Please provide the room ID', location='form')

    @api.expect(parser)
    @cross_origin()
    def post(self):
        args = self.parser.parse_args()
        room_id = args['room_id']

        try:
            # Panggil fungsi evaluate_question dari DatabaseOperations
            chat_transcripts = db_ops.get_chat_transcripts(room_id)
            starting_prompt = gpt_engine.initialize_evaluate_user_question(f"{chat_transcripts}")
            # print(starting_prompt)
            session['history'] = [{"role": "user", "content": starting_prompt}]
            
            answer, json_response = gpt_engine.hit_groq_api(session, one_time_message='')
            dict_form = gpt_engine.format_evaluate_user_question(answer)
            store_result = db_ops.store_evaluate_user_question(dict_form)
            return dict_form, 200
        except Exception as e:
            print(e)
            return jsonify({"message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=54322)