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
Session(app)
cors = CORS(app)
bi_gpt = bi_gpt_from_db()

api = Api(app, version='1.0', title='API Linov5 BI-GPT',
        description='Dokumentasi API Linov5 BI-GPT')
ns = api.namespace('LinovAIRecruitment', description='API Linov5 BI-GPT')

def create_parser(file_required, **extra_args):
    parser = reqparse.RequestParser()
    if file_required:
        parser.add_argument('cv_file', type=FileStorage, location='files', required=True, help='Upload Candidate CV')
    for name, details in extra_args.items():
        parser.add_argument(name, **details)
    return parser

@ns.route('/bi-gpt')
class create_cv_extractor(Resource):
    parser = create_parser(False,                              
                        question={'type': str, 'required': True, 'help': 'Question to Ask', 'location': 'form'},
                        table_name={'type': str, 'required': True, 'help': 'Nama Tabel Yang Ingin di Query', 'location': 'form'})
    @api.expect(parser)
    @cross_origin()

    def post(self):
        try:
            args = self.parser.parse_args()
            question, table_name = args['question'], args['table_name']
            result = bi_gpt.answer_question(question, table_name)
            return result, 200
        
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
if __name__ == '__main__':
    app.run(debug=True)