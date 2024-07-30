import sys, os, signal
from flask import Flask, session, request, jsonify, render_template, request
from flask_session import Session
from flask_cors import CORS, cross_origin
from flask_restx import Api, Resource, fields
from werkzeug.datastructures import FileStorage
from flask_restx import reqparse
from pathlib import Path
import uuid

module_dir = 'modules/'
modules_path = ['db', 'file_processor', 'gpt']
for mp in modules_path:
    mp = 'modules/' + mp + '_module/' 
    if mp not in sys.path:
        sys.path.append(mp)

from modules.db_module.db_manager import DatabaseOperations

db_ops = DatabaseOperations()

app = Flask(__name__)

app.config["SECRET_KEY"] = "virtual_assistant_ai"  # Replace with a real secret key
app.config["SESSION_TYPE"] = "filesystem"

def clear_sessions(signum, frame):
    os._exit(0)  # Use os._exit(0) to exit the application

# Register signal handler for SIGINT (CTRL+C) and SIGTERM
signal.signal(signal.SIGINT, clear_sessions)
signal.signal(signal.SIGTERM, clear_sessions)

Session(app)
cors = CORS(app)

api = Api(app, version='1.0', title='API for Virtual Assistant AI',
        description='Dokumentasi API Linov5 Virtual Assistant AI')
ns = api.namespace('Virtual Assistant', description='API For Virtual Assistant')

user_sessions = {}

@ns.route('/initialize', methods=['POST'])
class Initialize(Resource):
    @cross_origin()
    def post(self):
        try:
            # Buat user_id dan room_id baru menggunakan UUID
            user_id = str(uuid.uuid4())
            room_id = str(uuid.uuid4())
            
            # Simpan sesi pengguna
            result = db_ops.save_user_session(user_id, room_id)
            if result != "Success":
                return {'message': result}, 500
            
            # Simpan user_id dan room_id dalam variabel global
            user_sessions[user_id] = room_id
            
            return {
                'message': 'Initialization successful',
                'user_id': user_id,
                'room_id': room_id
            }, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400

@ns.route('/test', methods=['POST']) # POST
class api_demo(Resource):
    @cross_origin()
    def post(self):
        try:
            payload = request.json
            db_ops.upsert_dummy_data('Virtual Assistant', payload)
            return {'message': 'success'}, 200
        except Exception as e:
            print(e)
            return {'message': str(e)}, 400
        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)