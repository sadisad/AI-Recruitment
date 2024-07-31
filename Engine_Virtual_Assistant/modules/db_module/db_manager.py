import uuid
import pymongo
import json
import os
from datetime import datetime

from pymongo import ReturnDocument

class DatabaseOperations:
    def __init__(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.session_types = self.read_json_file(dir_path + '/schema_info.json')
        self.db_ai_mongo = self.connect_mongodb('mongo_db_virtual_assistant', dir_path)
    
    def connect_mongodb(self, conn_name, dir_path):
        credentials = self.read_json_file(dir_path + '/db_config.json')[conn_name]
        username = credentials['username']
        password = credentials['password']
        db_name = credentials['database']
        port = int(credentials['port'])
        host = credentials['host']
        
        if username != '':
            uri = f"mongodb://{username}:{password}@{host}:{port}/{db_name}"
        else:
            uri = f"mongodb://{host}:{port}/{db_name}"

        conn_client = pymongo.MongoClient(uri)
        db_mongo = conn_client[db_name]
        return db_mongo

    def read_json_file(self, file_name):
        with open(file_name) as f:
            file_content = json.load(f)
        return file_content
    
    def upsert_dummy_data(self, engine_type, input):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]

        dummy_entry = input

        try:
            result = tbl_mongo_ai.find_one_and_update(
                {"identifier_field": dummy_entry.get("identifier_field", "default_value")},  # Ganti dengan field identifier yang sesuai
                {"$set": dummy_entry},
                upsert=True
            )
            return "Success" if result else "No changes made"
        except Exception as e:
            print(f"Exception in upsert_dummy_data: {e}")
            return str(e)
        
    def save_user_session(self, user_id, room_id):
        session_data = {
            "user_id": user_id,
            "room_id": room_id,
            "timestamp": datetime.now()
        }
        try:
            self.db_ai_mongo["user_sessions"].insert_one(session_data)
            return "Success"
        except Exception as e:
            print(f"Exception in save_user_session: {e}")
            return str(e)


    def save_interaction(self, interaction):
        try:
            self.db_ai_mongo["interactions"].insert_one(interaction)
            return "Success"
        except Exception as e:
            print(f"Exception in save_interaction: {e}")
            return str(e)

            
    def store_to_db(self, engine_type, chat_type, session_id, log_file_content, dict_data={}, id_dict={}):
        last_updated = datetime.now()
        # unique_identifier = str(uuid.uuid4()) if engine_type != 'Form Filler' else dict_data['Name']
        unique_identifier = str(uuid.uuid4())
        id_tbl_value = session_id + '_' + unique_identifier if (chat_type == False) else session_id
        log_file_content = {'chat_transcript' : log_file_content}

        row_id = self.upsert_to_db_mongo(id_dict, engine_type, last_updated, dict_data, log_file_content=log_file_content)
        

        return row_id
    
    def upsert_to_db_mongo(self, checker_upsert, engine_type, last_updated, dict_result, log_file_content={}, id_kolom=''):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]
        final_dict = {**{"last_updated" : last_updated}, **dict_result}
        final_dict = {key.replace('.', ','): value for key, value in final_dict.items()} ## MongoDB does not support '.' in key names

        if id_kolom != '':
            final_dict['_id'] = final_dict[id_kolom]
            del final_dict[id_kolom]
        
        row_id = self.mongo_upsert_exception(checker_upsert, final_dict, tbl_mongo_ai)
        return row_id


    
    def mongo_upsert_exception(self, checker_upsert, final_dict, mongo_table):
        try:
            result = mongo_table.find_one_and_update(
                checker_upsert,
                {'$set': final_dict},
                upsert=True,
                return_document=ReturnDocument.AFTER
            ) 
            document_id = result['_id'] if result else None
            return document_id
        except Exception as e:
            print(f"MongoDB - Error in upsert exception: {str(e)}")
            return str(e)

    
    def upsert_conversation_transcript(self, room_id, message, role):
        tbl_mongo_ai = self.db_ai_mongo['user_sessions']
        
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timestamp_key = last_updated.replace(':', '_').replace('-', '_').replace(' ', '_')
        
        chat_entry = {
            f"chat_transcripts.{timestamp_key}.role": role,
            f"chat_transcripts.{timestamp_key}.content": message
        }
        
        try:
            result = tbl_mongo_ai.update_one(
                {"room_id": room_id},
                {"$set": chat_entry},
                upsert=False
            )
            return "Success" if result.modified_count else "No changes made"
        except Exception as e:
            print(f"MongoDB - Error in upsert chat transcripts: {str(e)}")
            return str(e)

