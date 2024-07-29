from flask import Flask, session, request
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource, fields
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
from bi_gpt_module import bi_gpt_from_db

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiramsa2024_gpt4"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "bi_gpt_session_folder"
app.config['APPLICATION_ROOT'] = '/bigpt'  # Set the application root to /bigpt
Session(app)

# Configure CORS
cors = CORS(app, resources={r"/bigpt/*": {"origins": "*"}})

# Initialize bi_gpt_from_db instance
bi_gpt = bi_gpt_from_db()

# Initialize API with custom prefix
api = Api(app, version='1.0', title='API Linov5 BI-GPT',
          description='Dokumentasi API Linov5 BI-GPT', prefix='/bigpt')

# Define namespace
ns = api.namespace('LinovBIGPT', description='API Linov5 BI-GPT')

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    if file_required:
        parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

@ns.route('/bi-gpt')
class CreateCVExtractor(Resource):
    parser = create_parser(False,
                           question={'type': str, 'required': True, 'help': 'Question to Ask', 'location': 'form'})

    @api.expect(parser)
    @cross_origin()
    def post(self):
        try:
            args = self.parser.parse_args()
            question = args['question']
            
            starting_prompt = bi_gpt.initialize_relevant_tables(question)
            
            session['history'] = [{"role": "user", "content": starting_prompt}]
            
            answer, json_response, table_names = bi_gpt.hit_openai_api(session, starting_prompt)
            
            print(answer)
            # print(json_response)
            
            for name in table_names:
                print(name)
            
            result = bi_gpt.answer_question(question, table_names)
            
            return result, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=54321, debug=True)