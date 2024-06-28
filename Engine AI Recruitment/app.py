from flask import Flask, session, request, jsonify, render_template
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource, fields
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
import os, json, shutil, signal, sys, ast
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

db_ops = DatabaseOperations()
file_handler = FileHandler()
gpt_engine = GPTEngine()

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "interview_session_folder"
Session(app)
cors = CORS(app)

api = Api(app, version='1.0', title='API Linov5 AI',
          description='Dokumentasi API Linov5 AI')
ns = api.namespace('LinovAIRecruitment', description='API For AI Recruitment')

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
    print(session['gpt_api_type'].split('_')[0])
    print(session['bool_chat'])
    print(session['gpt_api_type'])
    # to DB
    row_id = db_ops.store_to_db(session['gpt_api_type'].split('_')[0], 
                                session['bool_chat'], 
                                session['gpt_api_type'], 
                                log_file_content, 
                                dict_data=dict_form,
                                id_dict=primary_key)
    return dict_form, answer
    # return answer

def save_uploaded_file(file, id_cv):
    
    file_name = file.filename
    file_path = os.path.join(file_handler.dir_source, file_name)
    file.save(file_path)
    file_type, str_result = file_handler.checker_and_generator(file_name)
    file_handler.str_to_txt(file_type, file_name, str_result)
    user_response = str_result
    db_ops.mongo_upsert_exception({"id_cv" : id_cv}, {"file_path" : file_path, "str_content" : str_result}, db_ops.db_ai_mongo['cv_directories'])
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
    parser = create_parser(True,                              
                           cv_id={'type': str, 'required': True, 'help': 'ID CV File', 'location': 'form'},
                           fields_to_extract={'type': str, 'required': False, 'help': 'Contoh : name, phone_number, blood_type, experiences', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):
    
        try:
            args = self.parser.parse_args()
            uploaded_file = args['cv_file']
            id_cv = args['cv_id']
            
            try:
                if args['fields_to_extract']:
                    formatted_string = ', '.join(part.strip() for part in args['fields_to_extract'].split(','))
                    list_of_fields = [part.strip() for part in formatted_string.split(',')]
                else:
                    list_of_fields = []
            except:
                return {'message' : 'Masukkan fields_of_extract seperti contoh : name, phone_number, blood_type, experiences'}, 400

            session['usage'], session['bool_chat'] = [], False
            initialize_api_type('Form Filler')
            str_cv = save_uploaded_file(uploaded_file, id_cv)
            starting_prompt = gpt_engine.initialize_form_filler(list_form=list_of_fields)
            starting_prompt += '\n------\nCV:\n' + str_cv
            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"id_cv" : id_cv}, additional_dict={"id_cv" : id_cv})
            return dict_form, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_extractor/<string:cv_id>') # GET
class get_cv_extraction(Resource):
    # parser = create_parser(False, 
    #                           id_cv_extract={'type': str, 'required': True, 'help': 'ID untuk mengambil data hasil ekstraksi CV', 'location': 'form'})
    # @api.expect(parser)
    @api.expect()
    @cross_origin()

    def get(self, cv_id):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_extract'
            row_id = cv_id
            result = db_ops.get_row_data({'id_cv' : cv_id}, 'cv_form_filler', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_redflag') # POST
class create_cv_redflag(Resource):
    parser = create_parser(False, cv_id={'type': str, 'required': True, 'help': 'CV ID', 'location': 'form'}, 
                              job_id={'type': str, 'required': True, 'help': 'Job ID', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):

        try:
            args = self.parser.parse_args()
            cv_id = args['cv_id']
            job_id = args['job_id']

            session['usage'], session['bool_chat'] = [], False
            initialize_api_type('CV Redflags')

            try:
                str_cv = db_ops.get_row_data({'id_cv' : cv_id}, 'cv_directories', all_row=False)['str_content']
            except:
                return {"message" : "CV not found"}, 400
            
            try:
                session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy(job_id)
            except:
                return {"message" : "Job not found"}, 400

            starting_prompt = gpt_engine.initialize_redflags()
            starting_prompt += '\n------\nJob Vacancy:\n' + session['job_vacancy']
            starting_prompt += '\n------\nCV:\n' + str_cv

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"id_cv" : cv_id, "job_id" : job_id}, additional_dict={"id_cv" : cv_id, "job_id" : job_id})
            return dict_form, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_redflag/<string:cv_id>/<string:job_id>') # GET
class get_cv_redflag(Resource):
    # parser = create_parser(False, 
    #                           id_cv_redflag={'type': str, 'required': True, 'help': 'ID untuk mengambil hasil redflag CV', 'location': 'form'})
    # @api.expect(parser)
    @cross_origin()

    def get(self, cv_id, job_id):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_redflag']
            result = db_ops.get_row_data({'id_cv' : cv_id, "job_id" : job_id}, 'cv_redflags', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_scoring') # POST
class create_cv_scoring(Resource):
    parser = create_parser(False, cv_id={'type': str, 'required': True, 'help': 'CV ID', 'location': 'form'}, 
                              job_id={'type': str, 'required': True, 'help': 'Job ID', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            cv_id = args['cv_id']
            job_id = args['job_id']
            session['usage'], session['bool_chat'] = [], False

            try:
                str_cv = db_ops.get_row_data({'id_cv' : cv_id}, 'cv_directories', all_row=False)['str_content']
            except:
                return {"message" : "CV not found"}, 400
            
            try:
                session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy(job_id)
            except:
                return {"message" : "Job not found"}, 400
            
            initialize_api_type('One CV Reviewer')
            session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy(job_id)
            starting_prompt = gpt_engine.initialize_one_cv_reviewer()
            starting_prompt += '\n------\n' + session['job_vacancy']
            starting_prompt += '\n------\nCV:\n' + str_cv

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"id_cv" : cv_id, "job_id" : job_id}, additional_dict={"id_cv" : cv_id, "job_id" : job_id})
            return dict_form, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_scoring/<string:cv_id>/<string:job_id>') # GET
class get_cv_scoring(Resource):
    # parser = create_parser(False, 
    #                           id_cv_score={'type': str, 'required': True, 'help': 'ID untuk mengambil data hasil scoring CV', 'location': 'form'})
    # @api.expect(parser)
    @cross_origin()

    def get(self, cv_id, job_id):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_score']
            result = db_ops.get_row_data({'id_cv' : cv_id, "job_id" : job_id}, 'cv_scorer', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_scoring_by_job/<string:cv_id>/<string:job_id>') # GET
class get_cv_score_by_job(Resource):
    # parser = create_parser(False, 
    #                           id_cv_score={'type': str, 'required': True, 'help': 'ID untuk mengambil data hasil scoring CV', 'location': 'form'})
    # @api.expect(parser)
    @cross_origin()

    def get(self, cv_id, job_id):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_score']
            result = db_ops.get_row_data({'id_cv' : cv_id, "job_id" : job_id}, 'cv_scorer', all_row=False)
            try:
                keys_to_extract = ["name","job_title","skills", "skor_cv", "alasan"]
                result = {key: result[key] for key in keys_to_extract}
            except Exception as e:
                print(e)
            finally:
                return result, 200
            
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/cv_scoring_analysis/<string:cv_id>/<string:job_id>') # GET
class get_cv_scoring_analysis(Resource):
    # parser = create_parser(False, 
    #                           id_cv_score={'type': str, 'required': True, 'help': 'ID untuk mengambil data hasil scoring CV', 'location': 'form'})
    # @api.expect(parser)
    @cross_origin()
    def get(self, cv_id, job_id):
        try:
            # args = self.parser.parse_args()
            # row_id = args['id_cv_score']
            result = db_ops.get_row_data({'id_cv' : cv_id, "job_id" : job_id}, 'cv_scorer', all_row=False)
            try:
                keys_to_extract = ["kekurangan","kelebihan","total_masa_kerja_relevan", "kesimpulan", "alasan"]
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
    parser = create_parser(False, job_id={'type': str, 'required': True, 'help': 'Job ID', 'location': 'form'})
    
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            job_id = args['job_id']
            session['usage'], session['bool_chat'] = [], False
            
            try:
                session['job_id'], session['job_title'], session['job_vacancy'] = db_ops.get_job_vacancy(job_id)
            except:
                return {"message" : "Job not found"}, 400
            
            initialize_api_type('Questions')
            starting_prompt = gpt_engine.intialize_generate_question()
            starting_prompt += '\n------\n' + session['job_vacancy']

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"job_id" : job_id}, additional_dict={"job_id" : job_id})
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=54321, debug=True)

