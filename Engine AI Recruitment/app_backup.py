from flask import Flask, session, request, jsonify
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
import os, json, sys
from datetime import datetime, timedelta
import jwt
from threading import Timer
import uuid
import re
import traceback

# Path modules
modules_path = ['modules/db_module', 'modules/file_processor_module', 'modules/gpt_module']
for mp in modules_path:
    if mp not in sys.path:
        sys.path.append(mp)

from modules.db_module.db_manager import DatabaseOperations
from modules.file_processor_module.file_manager import FileHandler
from modules.gpt_module.gpt_manager import GPTEngine

db_ops = DatabaseOperations()
file_handler = FileHandler()
gpt_engine = GPTEngine()

# Initialize modules
db_ops = DatabaseOperations()
file_handler = FileHandler()
gpt_engine = GPTEngine()

app = Flask(__name__)

# Flask app configurations
app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with real secret key
app.config["SESSION_TYPE"] = "filesystem"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)
app.config["SESSION_FILE_DIR"] = "interview_session_folder"
app.config['SESSION_COOKIE_DOMAIN'] = '.linovhr.com'
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_PERMANENT'] = True

# Ensure the session directory exists
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
Session(app)

# CORS configuration
cors_origins = [
    "https://api-dev-airecruitment.linovhr.com", 
    "http://localhost:4200", 
    "https://dev5.linovhr.com", 
    "https://hcms.linovhr.com", 
    "https://dev-jobportal2.linovhr.com", 
    "https://jobportal2.linovhr.com", 
    "https://*.linovhr.com", 
    "http://172.31.48.31:54321", 
    "http://localhost:*"
]
CORS(app, supports_credentials=True, resources={r"/*": {"origins": cors_origins}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Your-Custom-Header')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS,PATCH')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# API documentation and security
api = Api(app, version='1.0', title='API Linov5 AI',
            description='Dokumentasi API Linov5 AI', 
            prefix='/api/v1',
            security='Bearer',
            authorizations={
                'Bearer': {
                'type': 'apiKey',
                'in': 'header',
                'name': 'Authorization',
                'description': 'Enter your Bearer token'
            }
        })

ns = api.namespace('LinovAIRecruitment', description='API For AI Recruitment')
ns_interview = api.namespace('LinovAIRecruitmentInterview', description='API For AI Recruitment Interview')

def clear_sessions(signum, frame):
    os._exit(0) 

# Helper function to initialize API type
def initialize_api_type(api_type):
    current_time = datetime.now().strftime("%H-%M-%S")
    session['gpt_api_type'] = f"{api_type}_{session.sid}_{current_time}"

def query_gpt(primary_key={}, additional_dict={}, one_time_message=''):
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
    
    # to DB
    row_id = db_ops.store_to_db(session['gpt_api_type'].split('_')[0], 
                                session['bool_chat'], 
                                session['gpt_api_type'], 
                                log_file_content, 
                                dict_data=dict_form,
                                id_dict=primary_key)
    return dict_form, answer

def save_uploaded_file(file, id_cv):
    
    file_name = file.filename
    file_path = os.path.join(file_handler.dir_source, file_name)
    file.save(file_path)
    file_type, str_result = file_handler.checker_and_generator(file_name)
    file_handler.str_to_txt(file_type, file_name, str_result)
    user_response = str_result
    db_ops.mongo_upsert_exception({"id_cv" : id_cv}, {"file_path" : file_path, "str_content" : str_result}, db_ops.db_recruitment['cv_directories'])
    return user_response

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    if file_required:
        parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

# Secret key loader
def load_secret_key():
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'modules', 'jwt_module', 'key_config.json')
        with open(file_path, 'r') as file:
            key_data = json.load(file)
            return key_data['SECRET_KEY']  # Return directly without base64 decoding
    except Exception as e:
        print(f"Error loading secret key: {e}")
        return None

SECRET_KEY = load_secret_key()

def decode_without_verification(token):
    try:
        decoded_data = jwt.decode(token, options={"verify_signature": False})
        # print(f"Decoded Data (Without Verification): {decoded_data}")

        # Don't attempt to decode the keys; just use them as they are
        decoded_claims = {}
        for key, value in decoded_data.items():
            decoded_claims[key] = value    
            # print(f"Key: {key}, Value: {value}")

        # print(f"Decoded Claims: {decoded_claims}")
        return decoded_claims
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None

# JWT token verification decorator
def token_required(f):
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            else:
                token = auth_header

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            decoded_claims = jwt.decode(token, options={"verify_signature": False})
            tenant_code = decoded_claims.get('mvjiWysucMzzxen46pJZng==', 'Unknown tenant')
            source = decoded_claims.get('21jl2CGx5yU9vq3ZQxkfcQ==', 'Unknown source')
            company_id = decoded_claims.get('WdZeiYKiPAIRjaCulcneFA==', 'Unknown company')

            if not tenant_code or not source or not company_id:
                return jsonify({'message': 'Invalid token claims!'}), 401

            # Store claims in session
            session['tenantCode'] = tenant_code
            session['source'] = source
            session['company'] = company_id

        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'message': f'Invalid token! {str(e)}'}), 401

        return f(*args, **kwargs)

    return decorated

def is_valid_cv(content):
    # Define basic keywords commonly found in CVs
    cv_keywords = ['experience', 'education', 'skills', 'contact', 'work history', 'career objective', 'professional summary']
    
    # Create a simple regex pattern for common sections found in resumes
    cv_patterns = [
        r'\bexperience\b',  # "Experience" section
        r'\beducation\b',    # "Education" section
        r'\bskills\b',       # "Skills" section
        r'\bwork\b',         # Words like "Work Experience"
        r'\bcontact\b',      # Contact Information
    ]
    
    # Convert content to lowercase for case-insensitive matching
    content = content.lower()
    
    # Check if at least one keyword exists in the content
    if any(re.search(pattern, content) for pattern in cv_patterns):
        return True
    return False

# Candidate CV extractor
@ns.route('/cv_extractor')  # POST
class create_cv_extractor(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    parser.add_argument('candidate_id', type=str, required=True, help='Candidate ID')

    @api.expect(parser)
    @cross_origin()
    @token_required
    def post(self):
        try:
            tenant = session.get('tenantCode')
            source = session.get('source')
            company = session.get('company')

            session['cv_extractor_usage'], session['cv_extractor_bool_chat'] = [], False
            initialize_api_type('Form Filler')

            args = self.parser.parse_args()
            uploaded_file = args['cv_file']
            candidate_id = args['candidate_id']

            # Check if candidate ID exists in cv_directories
            existing_record = db_ops.get_row_data({'candidate_id': candidate_id}, 'cv_directories', all_row=False)
            if existing_record and existing_record.get("message") != "Data not found":
                return {'message': f"Candidate ID {candidate_id} already exists."}, 400

            # Validate file type
            allowed_extensions = {'pdf', 'doc', 'docx'}
            file_extension = uploaded_file.filename.rsplit('.', 1)[-1].lower()
            if file_extension not in allowed_extensions:
                return {'message': f"Invalid file type: {file_extension}. Only PDF, DOC, and DOCX are allowed."}, 400

            # Save the uploaded file and its content
            id_cv = str(uuid.uuid4())
            str_cv = save_uploaded_file(uploaded_file, id_cv)

            # Validate CV content
            if not is_valid_cv(str_cv):
                return {'message': 'The uploaded file does not appear to be a valid CV or resume.'}, 400

            # Save CV content in the database
            db_ops.mongo_upsert_exception(
                {"candidate_id": candidate_id}, 
                {"id_cv": id_cv, "file_path": file_handler.dir_source, "str_content": str_cv, "tenant": tenant, "source": source, "company": company},
                db_ops.db_recruitment['cv_directories']
            )

            # Prepare prompt for GPT
            starting_prompt = gpt_engine.initialize_form_filler()
            starting_prompt += f'\n------\nCV:\n{str_cv}\nTenant: {tenant}\nSource: {source}\nCompany: {company}'
            session['history'] = [{"role": "user", "content": starting_prompt}]

            # Query GPT and return result
            dict_form, answer = query_gpt(
                primary_key={"candidate_id": candidate_id, "id_cv": id_cv},
                additional_dict={"candidate_id": candidate_id, "id_cv": id_cv}
            )
            return {"id_cv": id_cv, **dict_form}, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_extractor_multiple')  # POST
class create_cvs_extractor_multiple(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('cvs_file', type=FileStorage, location='files', action='append', required=True, help='CV files')  # Multiple files allowed
    
    @api.expect(parser)
    @cross_origin()
    @token_required  # Apply the token_required decorator to enforce JWT authentication
    def post(self):
        try:
            # Debug log for request inspection
            print("Files received: ", request.files)  # Check if files are being sent
            print("Form data received: ", request.form)   # Check if form data is being sent
            
            # Retrieve tenant, source, and company from the session (set after JWT is decoded)
            tenant = session.get('tenantCode')
            source = session.get('source')
            company = session.get('company')
            print(f"Tenant: {tenant}, Source: {source}, Company: {company}")

            # Initialize form filler session variables
            session['cv_extractor_usage'], session['cv_extractor_bool_chat'] = [], False
            initialize_api_type('Form Filler')
            
            # Parse files with parser
            args = self.parser.parse_args()
            uploaded_files = request.files.getlist("cvs_file")
            print("Uploaded files: ", uploaded_files)
            
            # Parse candidate_ids directly from form
            candidate_ids = request.form.get('candidate_ids', '').split(',')
            print("Candidate IDs: ", candidate_ids)
            
            if len(uploaded_files) != len(candidate_ids):
                print("Number of files and candidate IDs do not match")
                return {'message': 'The number of files does not match the number of candidate IDs.'}, 400

            responses = []
            allowed_extensions = {'pdf', 'doc', 'docx'}
            
            # Loop through each file and process them
            for idx, uploaded_file in enumerate(uploaded_files):
                print(f"Processing file {uploaded_file.filename} for candidate ID {candidate_ids[idx]}")
                candidate_id = candidate_ids[idx].strip()

                # Generate a unique id_cv for each CV extraction
                id_cv = str(uuid.uuid4())
                print(f"Generated id_cv: {id_cv}")
                
                # Check if the candidate_id already exists in cv_directories
                existing_record = db_ops.get_row_data({'candidate_id': candidate_id}, 'cv_directories', all_row=False)
                print(f"Existing record for {candidate_id}: {existing_record}")
                
                if existing_record and existing_record.get("message") != "Data not found":
                    responses.append({'candidate_id': candidate_id, 'message': f"Candidate ID {candidate_id} already exists.", 'status': 400})
                    continue
                
                # Check if the uploaded file is a valid CV format (PDF, DOC, DOCX)
                file_extension = uploaded_file.filename.rsplit('.', 1)[-1].lower()
                if file_extension not in allowed_extensions:
                    responses.append({'candidate_id': candidate_id, 'message': f"Invalid file type: {file_extension}. Only PDF, DOC, and DOCX are allowed.", 'status': 400})
                    continue

                # Extract content first without saving it
                file_name = uploaded_file.filename
                file_path = os.path.join(file_handler.dir_source, file_name)
                uploaded_file.save(file_path)
                print(f"File saved at {file_path}")

                # Validate the file content to ensure it looks like a CV or resume
                file_type, str_cv = file_handler.checker_and_generator(file_name)
                print(f"File content for {file_name}: {str_cv[:100]}...")  # Log first 100 chars for brevity
                if not is_valid_cv(str_cv):
                    responses.append({'candidate_id': candidate_id, 'message': 'The uploaded file does not appear to be a valid CV or resume.', 'status': 400})
                    continue

                # Reset session variables for usage tracking
                session['usage'], session['bool_chat'] = [], False
                initialize_api_type('Form Filler')

                # Save the valid file and extracted content in the database with the candidate ID
                file_handler.str_to_txt(file_type, file_name, str_cv)
                db_ops.mongo_upsert_exception(
                    {"candidate_id": candidate_id}, 
                    {
                        "id_cv": id_cv,
                        "file_path": file_path, 
                        "str_content": str_cv, 
                        "tenant": tenant, 
                        "source": source, 
                        "company": company
                    }, 
                    db_ops.db_recruitment['cv_directories']
                )
                print(f"Successfully saved CV for candidate {candidate_id}")

                # Prepare the starting prompt for the GPT engine
                starting_prompt = gpt_engine.initialize_form_filler()
                starting_prompt += '\n------\nCV:\n' + str_cv
                starting_prompt += f"\nTenant: {tenant}\nSource: {source}\nCompany: {company}\n------\nCV:\n{str_cv}"

                # Add the starting prompt to the session history
                session['history'] = [{"role": "user", "content": starting_prompt}]
                print(f"Starting prompt prepared for candidate {candidate_id}")

                # Interact with the GPT engine and generate the response
                dict_form, answer = query_gpt(
                    primary_key={"candidate_id": candidate_id, "id_cv": id_cv},
                    additional_dict={"candidate_id": candidate_id, "id_cv": id_cv}
                )
                print(f"GPT response received for candidate {candidate_id}")

                # Append the processed form data to the responses
                responses.append({"candidate_id": candidate_id, "id_cv": id_cv, **dict_form, 'status': 200})

            return {"results": responses}, 200
        
        except Exception as e:
            print("Error encountered: ", e)
            traceback.print_exc()  # Log the full traceback for the error
            return {'message': str(e)}, 400
        
@ns.route('/update_candidate_id/<string:candidate_id>')
class UpdateCandidateID(Resource):
    update_parser = api.parser()
    update_parser.add_argument('new_candidate_id', type=str, required=True, help='New Candidate ID', location='json')

    @api.expect(update_parser)
    @cross_origin()
    @token_required
    def put(self, candidate_id):
        try:
            # Retrieve the JSON payload from the request
            data = request.get_json()
            new_candidate_id = data.get('new_candidate_id')
            
            if not new_candidate_id:
                return {'message': 'New candidate ID is required'}, 400

            # Update the candidate_id in the cv_directories collection
            update_result_directories = db_ops.update_row_data(
                filter_criteria={'candidate_id': candidate_id},  # Find the document with the candidate_id
                update_data={'candidate_id': new_candidate_id},  # Update with the new candidate_id
                collection_name='cv_directories'
            )
            
            # Update the candidate_id in the cv_form_filler collection
            update_result_form_filler = db_ops.update_row_data(
                filter_criteria={'candidate_id': candidate_id},  # Find the document with the candidate_id
                update_data={'candidate_id': new_candidate_id},  # Update with the new candidate_id
                collection_name='cv_form_filler'
            )
            
            # Check if updates were successful in both collections
            if update_result_directories['modified_count'] > 0 or update_result_form_filler['modified_count'] > 0:
                return {'message': 'Candidate ID updated successfully in both collections.'}, 200
            else:
                return {'message': 'No matching document found to update in either collection.'}, 404

        except Exception as e:
            print(f"Error updating candidate ID: {e}")
            return {'message': str(e)}, 400
        
@ns.route('/cv_extractor_all')  # GET
class get_all_extracted_cv(Resource):
    @cross_origin()
    @token_required  
    def get(self):
        try:
            initialize_api_type('Form Filler')
            result = db_ops.get_all_extracted_cv()
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_extractor/<string:cv_id>')  # GET
class get_cv_extraction(Resource):
    @api.expect()
    @cross_origin()
    @token_required  
    def get(self, cv_id):
        try:
            row_id = cv_id
            result = db_ops.get_row_data({'id_cv': cv_id}, 'cv_form_filler', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/cv_extractor/<string:cv_id>', methods=['DELETE'])
class DeleteCV(Resource):
    @cross_origin()
    @token_required
    def delete(self, cv_id):
        try:
            result = db_ops.delete_cv_data(cv_id)
            if any(count > 0 for count in result.values()):
                return {'message': f'CV with id {cv_id} deleted successfully', 'details': result}, 200
            else:
                return {'message': f'CV with id {cv_id} not found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/candidate_redflags')  # POST
class create_candidate_redflags(Resource):
    parser = create_parser(False, 
                            candidate_id={'type': str, 'required': True, 'help': 'Candidate ID', 'location': 'form'}, 
                            job_desc={'type': str, 'required': True, 'help': 'Masukkan job description', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()
    @token_required  
    def post(self):
        try:
            # Retrieve tenant, source, and company from the session
            tenant = session.get('tenantCode')
            source = session.get('source')
            company = session.get('company')
            
            args = self.parser.parse_args()
            candidate_id = args['candidate_id']
            job_description = args['job_desc']
            
            session['job_vacancy'] = job_description
            
            session['usage'], session['bool_chat'] = [], False
            initialize_api_type('Candidate Redflags')

            candidate_data = db_ops.get_row_data({'candidate_id': candidate_id}, 'cv_directories', all_row=False)
            str_cv = candidate_data['str_content']
            id_cv = candidate_data['id_cv']

            starting_prompt = gpt_engine.initialize_candidate_redflags()
            starting_prompt += '\n------\nJob Vacancy:\n' + session['job_vacancy']
            starting_prompt += '\n------\nCV:\n' + str_cv
            starting_prompt += f'\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"candidate_id": candidate_id, "id_cv": id_cv},
                                        additional_dict={"candidate_id": candidate_id, "id_cv": id_cv, "tenant": tenant, "source": source, "company": company})
            
            # Save the response with tenant, source, and company
            db_ops.mongo_upsert_exception({"candidate_id": candidate_id, "id_cv": id_cv}, {
                "tenant": tenant,
                "source": source,
                "company": company
            }, db_ops.db_recruitment['candidate_redflags'])
            
            return dict_form, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_redflags/<string:candidate_id>') # GET
class get_candidate_redflags(Resource):
    @cross_origin()
    @token_required

    def get(self, candidate_id):
        try:
            result = db_ops.get_row_data({'candidate_id' : candidate_id}, 'candidate_redflags', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/candidate_redflags_all') # GET
class get_all_candidate_redflags_result(Resource):
    @cross_origin()
    @token_required
    def get(self):
        try:
            initialize_api_type('Candidate Redflags')
            result = db_ops.get_candidate_redflags()
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/candidate_redflags/<string:candidate_id>', methods=['DELETE'])
class DeleteCandidateRedflags(Resource):
    @cross_origin()
    @token_required
    def delete(self, candidate_id):
        try:
            # Delete redflags for a specific candidate
            result = db_ops.delete_row_data({'candidate_id': candidate_id}, 'candidate_redflags')
            if result.deleted_count > 0:
                return {'message': f'Redflags for candidate {candidate_id} deleted successfully'}, 200
            else:
                return {'message': f'Redflags for candidate {candidate_id} not found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_redflags/all', methods=['DELETE'])
class DeleteAllCandidateRedflags(Resource):
    @cross_origin()
    @token_required
    def delete(self):
        try:
            # Delete all redflags
            result = db_ops.delete_all_data('candidate_redflags')
            if result.deleted_count > 0:
                return {'message': 'All candidate redflags records deleted successfully'}, 200
            else:
                return {'message': 'No redflags records found to delete'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/toggle_redflag', methods=['POST'])
class ToggleRedflag(Resource):
    @cross_origin()
    @token_required
    def post(self):
        """
        Toggle the enabled/disabled status of multiple redflag configurations.
        """
        try:
            # Get the list of redflags and statuses from the request
            data = request.get_json()
            redflags = data.get('redflags')  # Expects a list of {"title": "high_turnover", "enabled": "yes"}

            if not isinstance(redflags, list):
                return jsonify({'message': 'Invalid input format. Expected a list of redflags.'}), 400
            
            config_dir = os.path.join(os.path.dirname(__file__), 'modules', 'gpt_module', 'prompts', 'Redflags')
            config_path = os.path.abspath(os.path.join(config_dir, 'redflag_config.json'))

            if not os.path.exists(config_path):
                return jsonify({'message': f"Configuration file {config_path} does not exist."}), 404

            with open(config_path, 'r') as f:
                redflag_config = json.load(f)

            updated_redflags = []

            # Iterate through the redflags to update them
            for redflag_data in redflags:
                title = redflag_data.get('title')
                new_status = redflag_data.get('enabled', '').lower()

                if not title or new_status not in ['yes', 'no']:
                    return jsonify({'message': f'Invalid input for {title}'}), 400

                # Find and update the redflag status
                updated = False
                for redflag in redflag_config:
                    if redflag['title'] == title:
                        redflag['enabled'] = new_status
                        updated_redflags.append(title)
                        updated = True
                        break

                if not updated:
                    return jsonify({'message': f'Redflag {title} not found'}), 404

            # Save the updated config back to the file
            with open(config_path, 'w') as f:
                json.dump(redflag_config, f, indent=4)

            # Provide a response after the updates
            return jsonify({'message': f'Redflags {updated_redflags} updated successfully'}), 200

        except FileNotFoundError as fnf_error:
            return jsonify({'message': str(fnf_error)}), 404
        except Exception as e:
            return jsonify({'message': str(e)}), 500

@ns.route('/candidate_ranker')  # POST
class create_candidate_ranker(Resource):
    # Updating the parser with new parameters
    parser = create_parser(False,
                            candidate_ids={'type': str, 'required': True, 'help': 'Daftar Candidate ID, dipisahkan dengan koma', 'location': 'form'},
                            job_requirements={'type': str, 'required': True, 'help': 'Masukkan Job Requirements', 'location': 'form'},
                            job_title={'type': str, 'required': True, 'help': 'Masukkan Job Title', 'location': 'form'},
                            job_description={'type': str, 'required': True, 'help': 'Masukkan Job Description atau Responsibilities', 'location': 'form'}
                            )

    @api.expect(parser)
    @cross_origin()
    @token_required
    def post(self):
        try:
            args = self.parser.parse_args()
            candidate_ids = args['candidate_ids'].split(', ')  # List of Candidate IDs separated by commas
            job_requirements = args['job_requirements']
            job_title = args['job_title']
            job_description = args['job_description']  # Job Description or Responsibilities

            # Store the session variables for job details
            session['job_vacancy'] = job_requirements
            session['job_title'] = job_title
            session['job_description'] = job_description
            session['usage'], session['bool_chat'] = [], False

            # Retrieve tenant, source, and company from the session
            tenant = session.get('tenantCode')
            source = session.get('source')
            company = session.get('company')

            ranking_results = []

            for candidate_id in candidate_ids:
                try:
                    # Fetch the relevant CV using candidate_id
                    candidate_data = db_ops.get_row_data({'candidate_id': candidate_id.strip()}, 'cv_directories', all_row=False)
                    str_cv = candidate_data['str_content']
                except Exception as e:
                    
                    ranking_results.append({"candidate_id": candidate_id, "message": f"CV for candidate id {candidate_id} not found"})
                    continue

                # Initialize the Candidate Ranker session for each candidate
                initialize_api_type('Candidate Ranker')

                # Build the starting prompt for GPT, incorporating job title and job requirements
                starting_prompt = gpt_engine.initialize_candidate_ranker()
                starting_prompt += f'\n------\nJob Title: {job_title}\nJob Requirements:\n{job_requirements}\nJob Description:\n{job_description}'
                starting_prompt += f'\n------\nCV:\n{str_cv}\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

                session['history'] = [{"role": "user", "content": starting_prompt}]

                # Query GPT and format the result using format_response_gpt
                dict_form, answer = query_gpt(primary_key={"candidate_id": candidate_id.strip()},
                                                additional_dict={"candidate_id": candidate_id.strip(), "tenant": tenant, "source": source, "company": company})
                formatted_result = gpt_engine.format_response_gpt(session, answer)
                ranking_results.append(dict_form)

            # Sort the results by score before returning them
            sorted_ranking_results = sort_by_score(ranking_results)

            for result in sorted_ranking_results:
                db_ops.upsert_to_db_mongo({'candidate_id': result['candidate_id']}, 'Candidate Ranker', datetime.now(), result)

            return sorted_ranking_results, 200

        except Exception as e:
            return {'message': str(e)}, 400

def sort_by_score(ranking_results):
    """
    Sorts the list of CV ranking results by the 'skor' field in descending order.
    
    Args:
        ranking_results (list): List of dictionaries containing CV ranking details.
        
    Returns:
        list: Sorted list of CV ranking results.
    """
    def extract_score(item):
        # Check if 'skor' exists and try to parse it
        if 'skor' in item and isinstance(item['skor'], str):
            try:
                # Extract the score as an integer from the string, assuming format 'xx/100'
                score_str = item['skor'].split('/')[0]
                return int(score_str)
            except (ValueError, IndexError):
                # If parsing fails, log and return a default score of 0
                return 0
        else:
            # Log missing 'skor' field and return a default score of 0
            return 0

    # Sort the list based on the extracted score in descending order
    sorted_results = sorted(ranking_results, key=extract_score, reverse=True)

    # Handle candidates with the same score by using additional criteria
    def resolve_ties(sorted_list):
        resolved_list = []
        previous_item = None

        for item in sorted_list:
            if previous_item and extract_score(previous_item) == extract_score(item):
                # Compare total_masa_kerja_relevan if scores are tied
                if 'total_masa_kerja_relevan' in item and 'total_masa_kerja_relevan' in previous_item:
                    if item['total_masa_kerja_relevan'] > previous_item['total_masa_kerja_relevan']:
                        resolved_list.append(item)
                    else:
                        resolved_list.append(previous_item)
                else:
                    resolved_list.append(item)
            else:
                resolved_list.append(item)
            previous_item = item

        return resolved_list

    sorted_results = resolve_ties(sorted_results)

    # Update the ranking based on the sorted order
    for index, item in enumerate(sorted_results, start=1):
        item['ranking'] = f"{index}"

    return sorted_results

@ns.route('/candidate_ranker/<string:candidate_id>', methods=['GET'])
class GetCandidateRanker(Resource):
    @cross_origin()
    @token_required
    def get(self, candidate_id):
        try:
            # Fetch the candidate ranker data for the given candidate ID
            result = db_ops.get_row_data({'candidate_id': candidate_id}, 'candidate_ranker', all_row=False)
            if result:
                return result, 200
            else:
                return {'message': f'Ranker data for candidate {candidate_id} not found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_ranker_all', methods=['GET'])
class GetAllCandidateRanker(Resource):
    @cross_origin()
    @token_required
    def get(self):
        try:
            # Fetch all candidate ranker data
            result = db_ops.get_all_data('candidate_ranker')
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_ranker/<string:candidate_id>', methods=['DELETE'])
class DeleteCandidateRanker(Resource):
    @cross_origin()
    @token_required
    def delete(self, candidate_id):
        try:
            # Delete the candidate ranker data for the given candidate ID
            result = db_ops.delete_row_data({'candidate_id': candidate_id}, 'candidate_ranker')
            if result.deleted_count > 0:
                return {'message': f'Ranker data for candidate {candidate_id} deleted successfully'}, 200
            else:
                return {'message': f'Ranker data for candidate {candidate_id} not found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_ranker/all', methods=['DELETE'])
class DeleteAllCandidateRanker(Resource):
    @cross_origin()
    @token_required
    def delete(self):
        try:
            # Delete all candidate ranker data
            result = db_ops.delete_all_data('candidate_ranker')
            if result.deleted_count > 0:
                return {'message': 'All candidate ranker records deleted successfully'}, 200
            else:
                return {'message': 'No candidate ranker records found to delete'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_profile_matching') # POST
class create_candidate_profile_matching(Resource):
    parser = create_parser(False, candidate_id={'type': str, 'required': True, 'help': 'Candidate ID', 'location': 'form'}, 
                            job_desc={'type': str, 'required': True, 'help': 'Masukkan Job Description', 'location': 'form'}, 
                            kriteria_pekerjaan={'type': str, 'required': True, 'help': 'Masukkan Kriteria Pekerjaan', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()
    @token_required
    def post(self):
        try:
            args = self.parser.parse_args()
            candidate_id = args['candidate_id']
            job_description = args['job_desc']
            kriteria_pekerjaan = args['kriteria_pekerjaan'].split('. ') 
            
            session['job_vacancy'] = job_description
            session['kriteria_pekerjaan'] = kriteria_pekerjaan
            
            session['usage'], session['bool_chat'] = [], False
            
            # Retrieve tenant, source, and company from the session
            tenant = session.get('tenantCode')
            source = session.get('source')
            company = session.get('company')
            
            try:
                candidate_data = db_ops.get_row_data({'candidate_id': candidate_id}, 'cv_directories', all_row=False)
                str_cv = candidate_data['str_content']
                id_cv = candidate_data['id_cv']  # Retrieve id_cv from candidate data
            except:
                return {"message": "CV not found"}, 400
            
            initialize_api_type('Candidate Profile Matching')
            starting_prompt = gpt_engine.initialize_candidate_profile_matching()
            starting_prompt += '\n------\n' + session['job_vacancy']
            starting_prompt += '\n------\nKriteria Pekerjaan:\n' + '\n'.join(session['kriteria_pekerjaan'])
            starting_prompt += '\n------\nCV:\n' + str_cv
            starting_prompt += f'\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

            session['history'] = [{"role": "user", "content": starting_prompt}]
            dict_form, answer = query_gpt(primary_key={"candidate_id": candidate_id, "id_cv": id_cv}, additional_dict={"candidate_id": candidate_id, "id_cv": id_cv, "tenant": tenant, "source": source, "company": company})
            
            dict_form["kriteria_pekerjaan"] = session['kriteria_pekerjaan']
            
            return dict_form, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_profile_matching/<string:candidate_id>') # GET
class get_candidate_profile_matching(Resource):
    @cross_origin()
    @token_required

    def get(self, candidate_id):
        try:
            result = db_ops.get_row_data({'candidate_id' : candidate_id}, 'candidate_profile_matching', all_row=False)
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/candidate_profile_matching/<string:candidate_id>', methods=['DELETE'])
class DeleteCandidateProfileMatching(Resource):
    @cross_origin()
    @token_required
    def delete(self, candidate_id):
        try:
            # Delete the profile matching data for the given candidate ID
            result = db_ops.delete_row_data({'candidate_id': candidate_id}, 'candidate_profile_matching')
            if result.deleted_count > 0:
                return {'message': f'Profile matching for candidate {candidate_id} deleted successfully'}, 200
            else:
                return {'message': f'Profile matching for candidate {candidate_id} not found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_profile_matching/all', methods=['DELETE'])
class DeleteAllCandidateProfileMatching(Resource):
    @cross_origin()
    @token_required
    def delete(self):
        try:
            # Delete all profile matching data
            result = db_ops.delete_all_data('candidate_profile_matching')
            if result.deleted_count > 0:
                return {'message': 'All candidate profile matching records deleted successfully'}, 200
            else:
                return {'message': 'No profile matching records found to delete'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/candidate_profile_matching_analysis/<string:candidate_id>') # GET
class get_candidate_profile_matching_analysis(Resource):
    @cross_origin()
    @token_required
    def get(self, candidate_id):
        try:
            result = db_ops.get_row_data({'candidate_id': candidate_id}, 'candidate_profile_matching', all_row=False)
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

@ns.route('/candidate_profile_matching/all') # GET
class get_all_candidate_profile_matching_result(Resource):
    
    @cross_origin()
    @token_required
    def get(self):
        try:
            initialize_api_type('Candidate Profile Matching')
            result = db_ops.get_candidate_profile_matching_result()
            
            # Ensure the result is JSON serializable
            serialized_result = [dict(r) for r in result]  # Adjust based on your ORM
            
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns.route('/sync_all_candidates', methods=['POST'])
class SyncAllCandidates(Resource):
    @cross_origin()
    @token_required
    def post(self):
        """
        Endpoint untuk melakukan sinkronisasi ulang semua kandidat terkait:
        1. Candidate Profile Matching
        2. Candidate Ranker
        3. Candidate Redflags
        """
        try:
            # Ambil tenant, source, dan company dari session (diset setelah JWT di-decode)
            tenant = session.get('tenantCode')
            source = session.get('source')
            company = session.get('company')

            # Ambil semua kandidat dari database 'cv_directories'
            all_candidates = db_ops.get_all_data('cv_directories')

            if not all_candidates:
                return {'message': 'Tidak ada kandidat yang ditemukan untuk sinkronisasi.'}, 404

            # Hasil sinkronisasi
            sync_results = {
                "profile_matching_updated": [],
                "candidate_ranker_updated": [],
                "redflags_updated": []
            }

            # Loop melalui semua kandidat untuk melakukan sinkronisasi
            for candidate in all_candidates:
                candidate_id = candidate['candidate_id']
                str_cv = candidate.get('str_content')
                id_cv = candidate.get('id_cv')

                # Proses ulang data untuk Profile Matching
                try:
                    # Ambil data pekerjaan dari session atau database (sesuaikan sesuai kebutuhan Anda)
                    job_description = session.get('job_vacancy', '')
                    kriteria_pekerjaan = session.get('kriteria_pekerjaan', [])

                    if not job_description or not kriteria_pekerjaan:
                        job_data = db_ops.get_row_data({'candidate_id': candidate_id}, 'candidate_profile_matching', all_row=False)
                        job_description = job_data.get('job_desc', '')
                        kriteria_pekerjaan = job_data.get('kriteria_pekerjaan', [])

                    starting_prompt = gpt_engine.initialize_candidate_profile_matching()
                    starting_prompt += '\n------\nJob Description:\n' + job_description
                    starting_prompt += '\n------\nKriteria Pekerjaan:\n' + '\n'.join(kriteria_pekerjaan)
                    starting_prompt += '\n------\nCV:\n' + str_cv
                    starting_prompt += f'\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

                    session['history'] = [{"role": "user", "content": starting_prompt}]
                    dict_form, answer = query_gpt(primary_key={"candidate_id": candidate_id, "id_cv": id_cv},
                                                additional_dict={"candidate_id": candidate_id, "id_cv": id_cv, "tenant": tenant, "source": source, "company": company})
                    
                    # Update hasil profile matching
                    db_ops.mongo_upsert_exception({"candidate_id": candidate_id}, dict_form, db_ops.db_recruitment['candidate_profile_matching'])
                    sync_results['profile_matching_updated'].append(candidate_id)
                except Exception as e:
                    print(f"Error during profile matching sync for candidate {candidate_id}: {e}")

                # Proses ulang data untuk Candidate Ranker
                try:
                    job_requirements = session.get('job_requirements', '')
                    job_title = session.get('job_title', '')

                    if not job_requirements or not job_title:
                        ranker_data = db_ops.get_row_data({'candidate_id': candidate_id}, 'candidate_ranker', all_row=False)
                        job_requirements = ranker_data.get('job_requirements', '')
                        job_title = ranker_data.get('job_title', '')

                    starting_prompt = gpt_engine.initialize_candidate_ranker()
                    starting_prompt += f'\n------\nJob Title: {job_title}\nJob Requirements:\n{job_requirements}'
                    starting_prompt += '\n------\nCV:\n' + str_cv
                    starting_prompt += f'\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

                    session['history'] = [{"role": "user", "content": starting_prompt}]
                    dict_form, answer = query_gpt(primary_key={"candidate_id": candidate_id, "id_cv": id_cv},
                                                 additional_dict={"candidate_id": candidate_id, "id_cv": id_cv, "tenant": tenant, "source": source, "company": company})
                    
                    # Update hasil candidate ranker
                    db_ops.mongo_upsert_exception({"candidate_id": candidate_id}, dict_form, db_ops.db_recruitment['candidate_ranker'])
                    sync_results['candidate_ranker_updated'].append(candidate_id)
                except Exception as e:
                    print(f"Error during candidate ranker sync for candidate {candidate_id}: {e}")

                # Proses ulang data untuk Redflags
                try:
                    starting_prompt = gpt_engine.initialize_candidate_redflags()
                    starting_prompt += '\n------\nJob Description:\n' + session.get('job_vacancy', '')
                    starting_prompt += '\n------\nCV:\n' + str_cv
                    starting_prompt += f'\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

                    session['history'] = [{"role": "user", "content": starting_prompt}]
                    dict_form, answer = query_gpt(primary_key={"candidate_id": candidate_id, "id_cv": id_cv},
                                                 additional_dict={"candidate_id": candidate_id, "id_cv": id_cv, "tenant": tenant, "source": source, "company": company})
                    
                    # Update hasil redflags
                    db_ops.mongo_upsert_exception({"candidate_id": candidate_id}, dict_form, db_ops.db_recruitment['candidate_redflags'])
                    sync_results['redflags_updated'].append(candidate_id)
                except Exception as e:
                    print(f"Error during redflag sync for candidate {candidate_id}: {e}")

            return jsonify({"message": "Sync process completed", "sync_results": sync_results}), 200

        except Exception as e:
            print(f"Error during sync process: {e}")
            return jsonify({'message': f'Something went wrong: {str(e)}'}), 500

@ns.route('/manual_candidate_input')  # POST
class ManualCandidateInput(Resource):
    parser = create_parser(False, 
                            company={'type': str, 'required': True, 'help': 'Company', 'location': 'form'},
                            fullName={'type': str, 'required': True, 'help': 'Full Name', 'location': 'form'},
                            gender={'type': str, 'required': True, 'help': 'Gender', 'location': 'form'},
                            documentType={'type': str, 'required': True, 'help': 'Document Type', 'location': 'form'},
                            idNumber={'type': str, 'required': True, 'help': 'ID Number', 'location': 'form'},
                            nationality={'type': str, 'required': True, 'help': 'Nationality', 'location': 'form'},
                            homeVillage={'type': str, 'required': True, 'help': 'Village (Home Address)', 'location': 'form'},
                            homeAddress={'type': str, 'required': True, 'help': 'Address (Home Address)', 'location': 'form'},
                            domicileVillage={'type': str, 'required': True, 'help': 'Village (Domicile Address)', 'location': 'form'},
                            domicileAddress={'type': str, 'required': True, 'help': 'Address (Domicile Address)', 'location': 'form'},
                            salutation={'type': str, 'required': False, 'help': 'Salutation', 'location': 'form'},
                            frontTitle={'type': str, 'required': False, 'help': 'Front Title', 'location': 'form'},
                            endTitle={'type': str, 'required': False, 'help': 'End Title', 'location': 'form'},
                            firstName={'type': str, 'required': False, 'help': 'First Name', 'location': 'form'},
                            vendor={'type': str, 'required': False, 'help': 'Vendor', 'location': 'form'},
                            lastName={'type': str, 'required': False, 'help': 'Last Name', 'location': 'form'},
                            nickname={'type': str, 'required': False, 'help': 'Nickname', 'location': 'form'},
                            position={'type': str, 'required': False, 'help': 'Position', 'location': 'form'},
                            photo={'type': str, 'required': False, 'help': 'Photo', 'location': 'form'},
                            status={'type': str, 'required': False, 'help': 'Status', 'location': 'form'},
                            tag={'type': str, 'required': False, 'help': 'Tag', 'location': 'form'},
                            birthplace={'type': str, 'required': False, 'help': 'Birthplace', 'location': 'form'},
                            birthdate={'type': str, 'required': False, 'help': 'Birthdate', 'location': 'form'},
                            religion={'type': str, 'required': False, 'help': 'Religion', 'location': 'form'},
                            ethnicity={'type': str, 'required': False, 'help': 'Ethnicity', 'location': 'form'},
                            maritalStatus={'type': str, 'required': False, 'help': 'Marital Status', 'location': 'form'},
                            medicalStatus={'type': str, 'required': False, 'help': 'Medical Status', 'location': 'form'},
                            bloodType={'type': str, 'required': False, 'help': 'Blood Type', 'location': 'form'},
                            height={'type': str, 'required': False, 'help': 'Height', 'location': 'form'},
                            weight={'type': str, 'required': False, 'help': 'Weight', 'location': 'form'},
                            houseStatus={'type': str, 'required': False, 'help': 'House Status', 'location': 'form'},
                            note={'type': str, 'required': False, 'help': 'Note', 'location': 'form'},
                            country={'type': str, 'required': False, 'help': 'Country', 'location': 'form'},
                            state={'type': str, 'required': False, 'help': 'State', 'location': 'form'},
                            city={'type': str, 'required': False, 'help': 'City', 'location': 'form'},
                            subDistrict={'type': str, 'required': False, 'help': 'Sub-District', 'location': 'form'},
                            postalCode={'type': str, 'required': False, 'help': 'Postal Code', 'location': 'form'},
                            since={'type': str, 'required': False, 'help': 'Since', 'location': 'form'},
                            phones={'type': str, 'required': False, 'help': 'Phones', 'location': 'form'},
                            phoneCode={'type': str, 'required': False, 'help': 'Phone Code', 'location': 'form'},
                            phoneNumber={'type': str, 'required': False, 'help': 'Phone Number', 'location': 'form'},
                            type={'type': str, 'required': False, 'help': 'Type', 'location': 'form'},
                            primary={'type': str, 'required': False, 'help': 'Primary', 'location': 'form'},
                            emails={'type': str, 'required': False, 'help': 'Emails', 'location': 'form'},
                            email={'type': str, 'required': False, 'help': 'Email', 'location': 'form'},
                            notification={'type': str, 'required': False, 'help': 'Notification', 'location': 'form'},
                            socialMedias={'type': str, 'required': False, 'help': 'Social Medias', 'location': 'form'},
                            socialMediaPlatform={'type': str, 'required': False, 'help': 'Social Media Platform', 'location': 'form'},
                            url={'type': str, 'required': False, 'help': 'URL', 'location': 'form'},
                            workExperience={'type': str, 'required': False, 'help': 'Work Experience', 'location': 'form'},
                            totalEmployee={'type': str, 'required': False, 'help': 'Total Employee', 'location': 'form'},
                            exitReason={'type': str, 'required': False, 'help': 'Exit Reason', 'location': 'form'},
                            startDate={'type': str, 'required': False, 'help': 'Start Date', 'location': 'form'},
                            current={'type': str, 'required': False, 'help': 'Current', 'location': 'form'},
                            endDate={'type': str, 'required': False, 'help': 'End Date', 'location': 'form'},
                            firstSalary={'type': str, 'required': False, 'help': 'First Salary', 'location': 'form'},
                            lastSalary={'type': str, 'required': False, 'help': 'Last Salary', 'location': 'form'},
                            currency={'type': str, 'required': False, 'help': 'Currency', 'location': 'form'},
                            companyType={'type': str, 'required': False, 'help': 'Company Type', 'location': 'form'},
                            responsibility={'type': str, 'required': False, 'help': 'Responsibility', 'location': 'form'},
                            reference={'type': str, 'required': False, 'help': 'Reference', 'location': 'form'},
                            formalEducation={'type': str, 'required': False, 'help': 'Formal Education', 'location': 'form'},
                            educationLevel={'type': str, 'required': False, 'help': 'Education Level', 'location': 'form'},
                            institution={'type': str, 'required': False, 'help': 'Institution', 'location': 'form'},
                            major={'type': str, 'required': False, 'help': 'Major', 'location': 'form'},
                            startYear={'type': str, 'required': False, 'help': 'Start Year', 'location': 'form'},
                            endYear={'type': str, 'required': False, 'help': 'End Year', 'location': 'form'},
                            graduateDate={'type': str, 'required': False, 'help': 'Graduate Date', 'location': 'form'},
                            gpa={'type': str, 'required': False, 'help': 'GPA', 'location': 'form'},
                            graduate={'type': str, 'required': False, 'help': 'Graduate', 'location': 'form'},
                            description={'type': str, 'required': False, 'help': 'Description', 'location': 'form'},
                            informalEducation={'type': str, 'required': False, 'help': 'Informal Education', 'location': 'form'},
                            subject={'type': str, 'required': False, 'help': 'Subject', 'location': 'form'},
                            hobbiesAndOtherActivities={'type': str, 'required': False, 'help': 'Hobbies And Other Activities', 'location': 'form'},
                            language={'type': str, 'required': False, 'help': 'Language', 'location': 'form'},
                            ratingListening={'type': str, 'required': False, 'help': 'Rating Listening', 'location': 'form'},
                            gradeListening={'type': str, 'required': False, 'help': 'Grade Listening', 'location': 'form'},
                            ratingWriting={'type': str, 'required': False, 'help': 'Rating Writing', 'location': 'form'},
                            gradeWriting={'type': str, 'required': False, 'help': 'Grade Writing', 'location': 'form'},
                            ratingReading={'type': str, 'required': False, 'help': 'Rating Reading', 'location': 'form'},
                            gradeReading={'type': str, 'required': False, 'help': 'Grade Reading', 'location': 'form'},
                            ratingSpeaking={'type': str, 'required': False, 'help': 'Rating Speaking', 'location': 'form'},
                            gradeSpeaking={'type': str, 'required': False, 'help': 'Grade Speaking', 'location': 'form'},
                            )

    @api.expect(parser)
    @cross_origin()
    @token_required
    def post(self):
        try:
            args = self.parser.parse_args()
            id_candidate = str(uuid.uuid4())
            id_cv = str(uuid.uuid4())  # Generate id_cv here
            
            candidate_data = {
                "_id": id_candidate,
                "id_candidate": id_candidate,
                "id_cv": id_cv,  # Assign the generated id_cv to the candidate
                "company": args['company'],
                "fullName": args['fullName'],
                "gender": args['gender'],
                "documentType": args['documentType'],
                "idNumber": args['idNumber'],
                "nationality": args['nationality'],
                "homeVillage": args['homeVillage'],
                "homeAddress": args['homeAddress'],
                "domicileVillage": args['domicileVillage'],
                "domicileAddress": args['domicileAddress'],
                "salutation": args.get('salutation', ''),
                "frontTitle": args.get('frontTitle', ''),
                "endTitle": args.get('endTitle', ''),
                "firstName": args.get('firstName', ''),
                "vendor": args.get('vendor', ''),
                "lastName": args.get('lastName', ''),
                "nickname": args.get('nickname', ''),
                "position": args.get('position', ''),
                "photo": args.get('photo', ''),
                "status": args.get('status', ''),
                "tag": args.get('tag', ''),
                "birthplace": args.get('birthplace', ''),
                "birthdate": args.get('birthdate', ''),
                "religion": args.get('religion', ''),
                "ethnicity": args.get('ethnicity', ''),
                "maritalStatus": args.get('maritalStatus', ''),
                "medicalStatus": args.get('medicalStatus', ''),
                "bloodType": args.get('bloodType', ''),
                "height": args.get('height', ''),
                "weight": args.get('weight', ''),
                "houseStatus": args.get('houseStatus', ''),
                "note": args.get('note', ''),
                "country": args.get('country', ''),
                "state": args.get('state', ''),
                "city": args.get('city', ''),
                "subDistrict": args.get('subDistrict', ''),
                "postalCode": args.get('postalCode', ''),
                "since": args.get('since', ''),
                "phones": args.get('phones', ''),
                "phoneCode": args.get('phoneCode', ''),
                "phoneNumber": args.get('phoneNumber', ''),
                "type": args.get('type', ''),
                "primary": args.get('primary', ''),
                "emails": args.get('emails', ''),
                "email": args.get('email', ''),
                "notification": args.get('notification', ''),
                "socialMedias": args.get('socialMedias', ''),
                "socialMediaPlatform": args.get('socialMediaPlatform', ''),
                "url": args.get('url', ''),
                "workExperience": args.get('workExperience', ''),
                "totalEmployee": args.get('totalEmployee', ''),
                "exitReason": args.get('exitReason', ''),
                "startDate": args.get('startDate', ''),
                "current": args.get('current', ''),
                "endDate": args.get('endDate', ''),
                "firstSalary": args.get('firstSalary', ''),
                "lastSalary": args.get('lastSalary', ''),
                "currency": args.get('currency', ''),
                "companyType": args.get('companyType', ''),
                "responsibility": args.get('responsibility', ''),
                "reference": args.get('reference', ''),
                "formalEducation": args.get('formalEducation', ''),
                "educationLevel": args.get('educationLevel', ''),
                "institution": args.get('institution', ''),
                "major": args.get('major', ''),
                "startYear": args.get('startYear', ''),
                "endYear": args.get('endYear', ''),
                "graduateDate": args.get('graduateDate', ''),
                "gpa": args.get('gpa', ''),
                "graduate": args.get('graduate', ''),
                "description": args.get('description', ''),
                "informalEducation": args.get('informalEducation', ''),
                "subject": args.get('subject', ''),
                "hobbiesAndOtherActivities": args.get('hobbiesAndOtherActivities', ''),
                "language": args.get('language', ''),
                "ratingListening": args.get('ratingListening', ''),
                "gradeListening": args.get('gradeListening', ''),
                "ratingWriting": args.get('ratingWriting', ''),
                "gradeWriting": args.get('gradeWriting', ''),
                "ratingReading": args.get('ratingReading', ''),
                "gradeReading": args.get('gradeReading', ''),
                "ratingSpeaking": args.get('ratingSpeaking', ''),
                "gradeSpeaking": args.get('gradeSpeaking', ''),
            }
            
            candidate_id = db_ops.insert_manual_candidate(candidate_data)
            
            # Save candidate's CV content if available and associate with id_cv
            if 'cv_file' in args:
                uploaded_file = args['cv_file']
                str_cv = save_uploaded_file(uploaded_file, id_cv)
                db_ops.mongo_upsert_exception({"id_cv": id_cv}, {"str_content": str_cv}, db_ops.db_recruitment['cv_directories'])

            return {'message': f'Manual Candidate {candidate_data["fullName"]} added successfully', 'id_candidate': str(candidate_id), 'id_cv': id_cv}, 200

        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

# --------------------------------------------- AI Interview ---------------------------------------------------

def query_gpt_interview(primary_key={}, additional_dict={}, one_time_message=''):
    # Memanggil API GPT untuk mendapatkan respons
    answer, json_response = gpt_engine.hit_groq_api(session, one_time_message)
    # answer, json_response = gpt_engine.hit_gpt_api(session, one_time_message)
    
    # Tangani key 'usage' dengan aman
    usage = json_response.get('usage', {})
    if 'usage' not in session:
        session['usage'] = []
    session['usage'].append(str(usage))
    
    # Simpan log chat
    log_file_content = file_handler.save_chat_transcript(session)
    
    # Format respons dari GPT
    dict_form, answer = gpt_engine.format_response_gpt(session, answer)
    dict_form = {**additional_dict, **dict_form}
    
    # Simpan hasil ke database
    row_id = db_ops.store_to_db(session['gpt_api_type'].split('_')[0],
                                session['bool_chat'],
                                session['gpt_api_type'],
                                log_file_content,
                                dict_data=dict_form,
                                id_dict=primary_key)
    
    # Simpan jawaban AI ke collection interview_transcripts
    db_ops.upsert_interview_chats('Interview', primary_key.get("room_id", "unknown_room_id"), answer, 'AI')

    return answer

def finish_interview(room_id):
    # Mengambil state sesi terakhir
    session_state = db_ops.get_session_state(room_id)

    if not session_state:
        print(f"Room ID {room_id} tidak ditemukan.")
        return {'message': f'Room ID {room_id} tidak ditemukan'}, 404

    # Mengambil data dari session state
    session['history'] = session_state['history']
    session['usage'] = session_state.get('usage', [])
    session['bool_chat'] = session_state.get('bool_chat', False)
    session['gpt_api_type'] = session_state.get('gpt_api_type', 'Interview')
    session['language'] = session_state.get('language', 'id')

    # Buat pesan akhir yang menyatakan wawancara selesai
    final_message = "--- WAWANCARA SELESAI ---\nJawaban kandidat dikumpulkan berdasarkan waktu yang tersedia."

    # Tambahkan pesan akhir ke riwayat wawancara
    session['history'].append({"role": "system", "content": final_message})

    # Simpan riwayat akhir wawancara ke database
    db_ops.upsert_interview_chats('Interview', room_id, final_message, 'AI')

    # Simpan status sesi yang diperbarui (sesi terakhir dengan tanda selesai)
    db_ops.update_session_state(room_id, {
        'history': session['history'],
        'usage': session['usage'],
        'bool_chat': session['bool_chat'],
        'gpt_api_type': session['gpt_api_type'],
        'language': session['language']
    })

    # Tampilkan log bahwa wawancara telah selesai
    print(f"Interview dengan room_id {room_id} selesai karena waktu habis.")

    return {'message': f'Interview dengan room_id {room_id} selesai karena waktu habis'}, 200

@ns_interview.route('/initialize_interview')
class InitializeInterview(Resource):
    parser = create_parser(False, candidate_id={'type': str, 'required': True, 'help': 'Candidate ID', 'location': 'form'}, 
                            job_desc={'type': str, 'required': True, 'help': 'Masukkan job description', 'location': 'form'},
                            duration={'type': int, 'required': False, 'help': 'Durasi Interview dalam menit', 'location': 'form'})

    @api.expect(parser)
    @cross_origin()
    @token_required
    def post(self):
        initialize_api_type('Interview_Transcript')

        args = self.parser.parse_args()
        candidate_id = args['candidate_id']
        job_desc = args['job_desc']
        interview_duration_minutes = args.get('duration', 60)  # Default duration is 60 minutes if not provided

        # Reset session state to ensure clean start
        session['usage'], session['bool_chat'] = [], False
        session['history'] = []  # Reset history for new interview
        room_id = str(uuid.uuid4())
        session['room_id'] = room_id

        # Retrieve tenant, source, and company from the session
        tenant = session.get('tenantCode')
        source = session.get('source')
        company = session.get('company')

        try:
            # Fetch CV content
            result = db_ops.get_row_data({'candidate_id': candidate_id}, 'cv_directories', all_row=False)
            str_cv = result['str_content']

            # Set language and load prompt
            session['language'] = 'id'  # Set to Indonesian language
            starting_prompt = gpt_engine.initialize_interview(str_cv, job_desc, interview_duration_minutes)
            
            # Append tenant, source, and company to the prompt
            starting_prompt += f'\nTenant: {tenant}\nSource: {source}\nCompany: {company}'

            # Set initial history and reset the finish state
            session['history'] = [{"role": "system", "content": starting_prompt}]
            session['interview_finished'] = False  # Ensure interview is marked as unfinished
            result = query_gpt_interview(primary_key={"room_id": room_id}, additional_dict={
                "candidate_id": candidate_id,
                "tenant": tenant, 
                "source": source, 
                "company": company
            })

            # Save chat and session information to the database
            db_ops.upsert_interview_chats('Interview', room_id, starting_prompt, 'AI')
            db_ops.upsert_interview_chats('Interview', room_id, result, 'AI')

            # Save the entire session state
            db_ops.update_session_state(room_id, {
                'history': session['history'],
                'usage': session['usage'],
                'bool_chat': session['bool_chat'],
                'gpt_api_type': session['gpt_api_type'],
                'language': session['language'],
                'interview_finished': False  # Save the finished state
            })

            # Set a timer for the interview duration to automatically finish the interview
            interview_duration_seconds = interview_duration_minutes * 60  # Convert to seconds
            Timer(interview_duration_seconds, finish_interview, args=[room_id]).start()

            return jsonify({"room_id": room_id, "message": result})

        except Exception as e:
            return {'message': str(e)}, 400

@ns_interview.route('/answer_interview')
class AnsweringInterview(Resource):
    parser = create_parser(False, room_id={'type': str, 'required': True, 'help': 'Masukkan room id', 'location': 'form'},
                            user_input={'type': str, 'required': True, 'help': 'Jawaban Kandidat', 'location': 'form'})
    
    @api.expect(parser)
    @cross_origin()
    @token_required
    def post(self):
        try:
            # Parsing args
            args = self.parser.parse_args()
            user_input = args['user_input']
            room_id = args['room_id']

            # Load session state
            session_state = db_ops.get_session_state(room_id)

            if not session_state:
                return jsonify({'message': 'Room tidak ditemukan'}), 404

            # Cek apakah interview sudah selesai
            if session_state.get('interview_finished', False):
                return jsonify({"message": "Interview telah selesai, tidak dapat menerima jawaban tambahan"}), 400

            # Validate UUID format for room_id
            try:
                uuid.UUID(room_id)
            except ValueError:
                return jsonify({'message': 'Invalid room_id format, must be a valid UUID'}), 400

            # Restore session state
            session['history'] = session_state['history']
            session['usage'] = session_state['usage']
            session['bool_chat'] = session_state['bool_chat']
            session['gpt_api_type'] = session_state['gpt_api_type']
            session['language'] = session_state['language']
            session['room_id'] = room_id

            # Append user input to session history
            session['history'].append({"role": "user", "content": user_input})

            # Save candidate's response to the database
            db_ops.upsert_interview_chats('Interview', room_id, user_input, 'candidate')

            # Check if the interview has already started to avoid repeating introduction
            if session_state.get('interview_started', False):
                # Query GPT for the next question
                result = query_gpt_interview(primary_key={"room_id": room_id}, additional_dict={
                    "tenant": session.get('tenantCode'), 
                    "source": session.get('source'), 
                    "company": session.get('company')
                })
            else:
                # If the interview is just starting, set the flag and ask the first question
                result = query_gpt_interview(primary_key={"room_id": room_id}, additional_dict={
                    "tenant": session.get('tenantCode'), 
                    "source": session.get('source'), 
                    "company": session.get('company')
                })
                # Mark interview as started
                session_state['interview_started'] = True
                db_ops.update_session_state(room_id, session_state)

            # Append the AI's response to session history
            session['history'].append({"role": "system", "content": result})

            # Save the updated session state
            db_ops.update_session_state(room_id, {
                'history': session['history'],
                'usage': session['usage'],
                'bool_chat': session['bool_chat'],
                'gpt_api_type': session['gpt_api_type'],
                'language': session['language'],
                'interview_started': session_state['interview_started']  # Ensure the interview start flag is saved
            })

            # Return the next question as the response
            return jsonify({"next_question": result})
        
        except Exception as e:
            return jsonify({'message': f'Something went wrong: {str(e)}'}), 500

@ns_interview.route('/interviews/room/<string:room_id>')
class GetInterviewRoomId(Resource):
    @api.expect()
    @cross_origin()
    @token_required

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
    @token_required
    def get(self):
        try:
            result = db_ops.get_all_room_interview()
            return jsonify(result), 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
@ns_interview.route('/interview/<string:room_id>', methods=['DELETE'])
class DeleteInterview(Resource):
    @cross_origin()
    @token_required
    def delete(self, room_id):
        try:
            # Hapus interview berdasarkan room_id
            result = db_ops.delete_row_data({'room_id': room_id}, 'interview_transcripts')
            if result.deleted_count > 0:
                return {'message': f'Interview with room_id {room_id} deleted successfully'}, 200
            else:
                return {'message': f'Interview with room_id {room_id} not found'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns_interview.route('/interviews', methods=['DELETE'])
class DeleteAllInterviews(Resource):
    @cross_origin()
    @token_required
    def delete(self):
        try:
            # Hapus semua interview
            result = db_ops.delete_all_data('interview_transcripts')
            if result.deleted_count > 0:
                return {'message': f'All interviews deleted successfully'}, 200
            else:
                return {'message': 'No interviews found to delete'}, 404
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=54321, debug=False)