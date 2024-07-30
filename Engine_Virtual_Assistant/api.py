import sys, os, signal
from flask import Flask, session, request, jsonify
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource
import uuid
from modules.ai_module.llm import LanguageModel
from modules.db_module.db_manager import DatabaseOperations

app = Flask(__name__)

app.config["SECRET_KEY"] = "virtual_assistant_ai"  # Ganti dengan kunci rahasia yang sebenarnya
app.config["SESSION_TYPE"] = "filesystem"

def clear_sessions(signum, frame):
    os._exit(0)  # Gunakan os._exit(0) untuk keluar dari aplikasi

# Register signal handler untuk SIGINT (CTRL+C) dan SIGTERM
signal.signal(signal.SIGINT, clear_sessions)
signal.signal(signal.SIGTERM, clear_sessions)

Session(app)
cors = CORS(app)

api = Api(app, version='1.0', title='API for Virtual Assistant AI',
          description='Dokumentasi API Linov5 Virtual Assistant AI')
ns = api.namespace('virtual_assistant', description='API For Virtual Assistant')

db_ops = DatabaseOperations()
ai_engine = LanguageModel()
user_sessions = {}

@ns.route('/initialize', methods=['POST'])
class Initialize(Resource):
    @cross_origin()
    def post(self):
        try:
            # Buat user_id dan room_id baru menggunakan UUID
            user_id = str(uuid.uuid4())
            room_id = str(uuid.uuid4())
            
            prompt = ai_engine.initialize_prompt()

            # Dapatkan sapaan awal dari LLM
            llm_response, dict = ai_engine.generate_response(prompt)
            
            print(llm_response, dict)
            
            # Simpan sesi pengguna
            result = db_ops.save_user_session(user_id, room_id)
            if result != "Success":
                print(f"Error saving session: {result}")
                return {'message': result}, 500
            
            # Simpan user_id dan room_id dalam variabel global
            user_sessions[user_id] = room_id
            
            return {
                'message': 'Initialization successful',
                'user_id': user_id,
                'room_id': room_id,
                'llm_response': llm_response
            }, 200
        except Exception as e:
            print(f"Exception in /initialize: {e}")
            return {'message': str(e)}, 400

@ns.route('/test', methods=['POST'])
class Test(Resource):
    @cross_origin()
    def post(self):
        try:
            payload = request.json
            result = db_ops.save_interaction(payload)
            if result == "Success":
                return {'message': 'success'}, 200
            else:
                return {'message': result}, 500
        except Exception as e:
            print(f"Exception in /test: {e}")
            return {'message': str(e)}, 400
        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
