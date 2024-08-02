from flask import Flask, session, request, jsonify, render_template
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource, fields
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
import os, json, shutil, signal, sys, ast
from datetime import date, datetime
from pathlib import Path

import uuid
from bson import Binary
from bson.binary import UuidRepresentation

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

app = Flask(__name__)

app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "interview_session_folder"

# Ensure the directory exists when initializing the app
Path(app.config["SESSION_FILE_DIR"]).mkdir(parents=True, exist_ok=True)

Session(app)
cors = CORS(app)

api = Api(app, version='1.0', title='API Linov5 AI',
        description='Dokumentasi API Linov5 AI')
ns = api.namespace('LinovAIRecruitment', description='API For AI Recruitment')
ns_interview = api.namespace('LinovAIRecruitmentInterview', description='API For AI Recruitment Interview')

def clear_sessions(signum, frame):
    # session_dir = app.config["SESSION_FILE_DIR"]
    # if os.path.isdir(session_dir):
    #     shutil.rmtree(session_dir)
    #     print("Session storage cleared.")
    # else:
    #     print(f"Session storage directory '{session_dir}' does not exist.")
    os._exit(0)  # Use os._exit(0) to exit the application

# Register signal handler for SIGINT (CTRL+C) and SIGTERM
signal.signal(signal.SIGINT, clear_sessions)
signal.signal(signal.SIGTERM, clear_sessions)

def initialize_api_type(api_type):
    current_time = datetime.now().strftime("%H-%M-%S")
    session['gpt_api_type'] =  api_type + '_' + str(session.sid) + '_' +  current_time

def query_gpt(primary_key={}, additional_dict={}, one_time_message='', companyId=''):
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
    print(session['gpt_api_type'].split('_')[0])
    print(session['bool_chat'])
    print(session['gpt_api_type'])
    # to DB
    row_id = db_ops.store_to_db(companyId, session['gpt_api_type'].split('_')[0], 
                                session['bool_chat'], 
                                session['gpt_api_type'], 
                                log_file_content, 
                                dict_data=dict_form,
                                id_dict=primary_key,
                                )
    
    return dict_form, answer
    # return answer

def save_uploaded_file(file, id_cv, companyId):
    file_name = file.filename
    dir_path = os.path.join(file_handler.dir_source, companyId)

    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, file_name)
    file.save(file_path)

    file_type, str_result = file_handler.checker_and_generator(file_name)
    file_handler.str_to_txt(file_type, file_name, str_result)

    user_response = str_result
    db_ops.mongo_upsert_exception({"id_cv": id_cv}, {"file_path": file_path, "str_content": str_result}, db_ops.db_ai_mongo[f'{companyId}_cvDirectories'])
    
    return user_response

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    if file_required:
        parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

@ns.route('/cv_extractor') # POST
class create_cv_extractor(Resource):
    parser = create_parser(True, companyId={'type': str, 'required': True, 'help': 'input company id', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):
    
        try:
            args = self.parser.parse_args()
            uploaded_file = args['cv_file']
            companyId = args['companyId']
            
            id_cv = str(uuid.uuid4())

            session['usage'], session['bool_chat'] = [], False
            initialize_api_type('Form Filler')
            str_cv = save_uploaded_file(uploaded_file, id_cv, companyId)
            starting_prompt = gpt_engine.initialize_form_filler()
            starting_prompt += '\n------\nCV:\n' + str_cv
            
            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"id_cv" : id_cv}, additional_dict={"id_cv" : id_cv}, companyId=companyId)

            return dict_form, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/all_cv/<string:companyId>') # GET
class get_all_extracted_cv(Resource):
    @cross_origin()
    def get(self, companyId):
        try:
            initialize_api_type('Form Filler')
            result = db_ops.get_all_extracted_cv(companyId)
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
            

@ns.route('/cv_extractor/<string:cv_id>/company_<string:companyId>', methods=['GET'])
class get_cv_extraction(Resource):

    @cross_origin()
    def get(self, cv_id, companyId):
        try:
            if not cv_id or not companyId:
                return {'message': 'cv_id and companyId are required'}, 400

            result = db_ops.get_row_data({'id_cv': cv_id}, f'{companyId}_cvFormFiller', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_redflag') # POST
class create_cv_redflag(Resource):
    parser = create_parser(False, cv_id={'type': str, 'required': True, 'help': 'CV ID', 'location': 'form'}, 
                              job_desc={'type': str, 'required': True, 'help': 'masukkan job description', 'location': 'form'},
                              companyId={'type': str, 'required': True, 'help': 'masukkan companyId', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):

        try:
            args = self.parser.parse_args()
            cv_id = args['cv_id']
            job_description = args['job_desc']
            companyId = args['companyId']
            
            session['job_vacancy'] = job_description

            session['usage'], session['bool_chat'] = [], False
            initialize_api_type('CV Redflags')

            try:
                str_cv = db_ops.get_row_data({'id_cv' : cv_id}, f'{companyId}_cvDirectories', all_row=False)['str_content']
            except:
                return {"message" : "CV not found"}, 400

            starting_prompt = gpt_engine.initialize_redflags()
            starting_prompt += '\n------\nJob Vacancy:\n' + session['job_vacancy']
            starting_prompt += '\n------\nCV:\n' + str_cv

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"id_cv" : cv_id}, additional_dict={"id_cv" : cv_id}, companyId=companyId)
            return dict_form, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_redflag/<string:cv_id>/company_<string:companyId>') # GET
class get_cv_redflag(Resource):
    # parser = create_parser(False, 
    #                           id_cv_redflag={'type': str, 'required': True, 'help': 'ID untuk mengambil hasil redflag CV', 'location': 'form'})
    # @api.expect(parser)
    @cross_origin()

    def get(self, cv_id, companyId):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_redflag']
            result = db_ops.get_row_data({'id_cv' : cv_id}, f'{companyId}_cvRedflags', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_scoring') # POST
class create_cv_scoring(Resource):
    parser = create_parser(False, cv_id={'type': str, 'required': True, 'help': 'CV ID', 'location': 'form'}, 
                              job_desc={'type': str, 'required': True, 'help': 'masukkan job description', 'location': 'form'},
                              companyId={'type': str, 'required': True, 'help': 'masukkan companyId', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            cv_id = args['cv_id']
            job_description = args['job_desc']
            companyId = args['companyId']
            
            session['job_vacancy'] = job_description
            
            session['usage'], session['bool_chat'] = [], False
            
            try:
                str_cv = db_ops.get_row_data({'id_cv' : cv_id}, f'{companyId}_cvDirectories', all_row=False)['str_content']
            except:
                return {"message" : "CV not found"}, 400
            
            initialize_api_type('One CV Reviewer')
            # session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy(job_id)
            starting_prompt = gpt_engine.initialize_one_cv_reviewer()
            starting_prompt += '\n------\n' + session['job_vacancy']
            starting_prompt += '\n------\nCV:\n' + str_cv

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"id_cv" : cv_id}, additional_dict={"id_cv" : cv_id}, companyId=companyId)
            return dict_form, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_scoring/<string:cv_id>/company_<string:companyId>') # GET
class get_cv_scoring(Resource):
    @cross_origin()

    def get(self, cv_id, companyId):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_score']
            result = db_ops.get_row_data({'id_cv' : cv_id}, f'{companyId}_cvScorer', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_scoring_analysis/<string:cv_id>/company_<string:companyId>') # GET
class get_cv_scoring_analysis(Resource):
    @cross_origin()
    def get(self, cv_id, companyId):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_score']
            result = db_ops.get_row_data({'id_cv' : cv_id}, f'{companyId}_cvScorer', all_row=False)
            try:
                keys_to_extract = ["kekurangan","kelebihan", "skor_cv","total_masa_kerja_relevan", "kesimpulan", "alasan"]
                result = {key: result[key] for key in keys_to_extract}
            except Exception as e:
                print(e)
            finally:
                return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/job_vacancy')
class create_job_vacancy(Resource):
    parser = create_parser(False, job_id={'type': str, 'required': True, 'help': 'Job ID', 'location': 'form'}, 
                            job_title={'type': str, 'required': True, 'help': 'Posisi Yang Dilamar', 'location': 'form'},
                            role_overview={'type': str, 'required': True, 'help': 'Deskripsi Singkat Pekerjaan', 'location': 'form'},
                            responsibilities={'type': str, 'required': True, 'help': 'Tanggung Jawab dari Pekerjaan', 'location': 'form'},
                            qualifications={'type': str, 'required': True, 'help': 'Kualifikasi Pekerjaan', 'location': 'form'})
    
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            db_ops.mongo_upsert_exception({"job_id" : args['job_id']}, 
                                        {"job_title" : args['job_title'], 
                                        "role_overview" : args['role_overview'],
                                        "responsibilities" : args['responsibilities'],
                                        "qualifications" : args['qualifications']},
                                        db_ops.db_ai_mongo['job_vacancy'])
            return {'message' : 'Create Job ' +  args['job_title'] + ' Succesful.'}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/job_vacancy/<string:job_id>')
class get_job_vacancy(Resource):
    # parser = create_parser(False, 
    #                           id_cv_score={'type': str, 'required': True, 'help': 'ID untuk mengambil data hasil scoring CV', 'location': 'form'})
    # @api.expect(parser)
    @cross_origin()
    def get(self, job_id):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_score']
            result = db_ops.get_row_data({'job_id' : job_id}, 'job_vacancy', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
# TASK post & get to create question based on job_id 
@ns.route('/interview_questions') #POST
class create_interview_questions(Resource):
    parser = create_parser(False, job_id={'type': str, 'required': True, 'help': 'Job ID', 'location': 'form'}, job_desc={'type': str, 'required': True, 'help': 'masukkan job description', 'location': 'form'})
    # parser = create_parser(False, job_id={'type': str, 'required': True, 'help': 'Job ID', 'location': 'form'})
    
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            job_id = args['job_id']
            job_description = args['job_desc']
            
            session['job_vacancy'] = job_description
            
            session['usage'], session['bool_chat'] = [], False
            
            initialize_api_type('Questions')
            starting_prompt = gpt_engine.intialize_generate_question()
            starting_prompt += '\n------\n' + session['job_vacancy']

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"job_id" : job_id, "job_description": job_description}, additional_dict={"job_id" : job_id, "job_description": job_description})
            return dict_form, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/interview_questions/<string:job_id>')
class get_interview_questions(Resource):
    @cross_origin()

    def get(self, job_id):
        
        try:
            result = db_ops.get_row_data({'job_id' : job_id}, 'interview_questions', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_scoring/all/<string:companyId>') # GET
class get_all_cv_scoring_result(Resource):
    @cross_origin()
    def get(self, companyId):
        try:
            initialize_api_type('One CV Reviewer')
            result = db_ops.get_cv_scoring_result(companyId)
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_red_flags/all/<string:companyId>') # GET
class get_all_cv_redflags_result(Resource):
    @cross_origin()
    def get(self, companyId):
        try:
            initialize_api_type('CV Redflags')
            result = db_ops.get_cv_redflags(companyId)
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
################### AI INTERVIEW #################

def query_gpt_interview(primary_key={}, additional_dict={}, one_time_message='', companyId=''):
    
    # answer, json_response = gpt_engine.hit_gpt_api(session, one_time_message)
    answer, json_response = gpt_engine.hit_groq_api(session, one_time_message)
    
    session['history'].append({"role": "system", "content": answer})
    
    usage = json_response.get('usage', {})
    session['usage'].append(str(usage))
    log_file_content = file_handler.save_chat_transcript(session)
    dict_form, answer = gpt_engine.format_response_gpt(session, answer)
    dict_form = {**additional_dict, **dict_form}
    row_id = db_ops.store_to_db(companyId, session['gpt_api_type'].split('_')[0],
                                session['bool_chat'],
                                session['gpt_api_type'],
                                log_file_content,
                                dict_data=dict_form,
                                id_dict=primary_key)
    
    return answer
@ns_interview.route('/initialize_interview')
class IntitializeInterview(Resource):
    parser = create_parser(False, cv_id={'type': str, 'required': True, 'help': 'CV ID', 'location': 'form'}, 
                              job_desc={'type': str, 'required': True, 'help': 'masukkan job description', 'location': 'form'},
                              companyId={'type': str, 'required': True, 'help': 'masukkan companyId', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()
    def post(self):
        initialize_api_type('Interview_Transcript')
        
        args = self.parser.parse_args()
        cv_id = args['cv_id']
        job_desc = args['job_desc']
        companyId = args['companyId']
        
        session['usage'], session['bool_chat'] = [], False
        
        room_id = str(uuid.uuid4())
        session['room_id'] = room_id
        
        try:
            result = db_ops.get_row_data({'id_cv' : cv_id}, f'{companyId}_cvDirectories', all_row=False)
            str_cv = result['str_content']

            starting_prompt = gpt_engine.initialize_interview(str_cv, job_desc)
            session['history'] = [{"role": "user", "content": starting_prompt}]
            result = query_gpt_interview(primary_key={"room_id": room_id}, additional_dict={"cv_id": cv_id}, companyId=companyId)
            db_ops.upsert_interview_chats('Interview', room_id, result, 'AI', companyId)
            
            return jsonify({"room_id": room_id, "message": result})
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
    
@ns_interview.route('/answer_interview')
class AnsweringInterview(Resource):
    parser = create_parser(False, room_id={'type': str, 'required': True, 'help': 'Masukkan room id', 'location': 'form'},
                           user_input={'type': str, 'required': True, 'help': 'User Answer', 'location': 'form'},
                           companyId={'type': str, 'required': True, 'help': 'companyId', 'location': 'form'})
    
    @api.expect(parser)
    @cross_origin()
    def post(self):
        
        initialize_api_type('Interview_Transcript')
        
        args = self.parser.parse_args()
        user_input = args['user_input']
        room_id = args['room_id']
        companyId = args['companyId']
        
        session['usage'], session['bool_chat'] = [], False
        
        get_room = db_ops.get_row_data({"room_id": room_id}, f'{companyId}_interviewTranscripts', all_row=False)
        
        if "message" in get_room and get_room["message"] == "Data not found":
            print({'message': 'Data not found'})
            return jsonify({'message': 'room not found'}), 500
        
        try:
            
            db_ops.upsert_interview_chats('Interview', room_id, user_input, 'candidate', companyId)
            
            session['history'].append({"role": "user", "content": user_input})
            
            result = query_gpt_interview(primary_key={"room_id": room_id} , companyId=companyId)
            
            db_ops.upsert_interview_chats('Interview', room_id, result, 'AI', companyId)
            
            return jsonify({"next_question": result})
        
        except Exception as e:
            print(e)
            return {'message': str(e)}
        
@ns_interview.route('/interviews/room/<string:room_id>')
class GetInterviewRoomId(Resource):
    @api.expect()
    @cross_origin()

    def get(self, room_id):
        try:
            result = db_ops.get_row_data({'room_id' : room_id}, 'interview_transcripts', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns_interview.route('/interviews/rooms')
class GetAllInterviewRoom(Resource):
    @cross_origin()
    def get(self):
        try:
            result = db_ops.get_all_room_interview()
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=54321, debug=True)

