import pymongo
import json
import os
import datetime

class DatabaseOperations:
    def __init__(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.session_types = self.read_json_file(dir_path + '/schema_info.json')
        self.db_ai_mongo = self.connect_mongodb('mongo_db_virtual_assistant', dir_path)
        ### Jangan pernah cursor di atas begini, bikin cursor, langsung close tiap query. Jgn 1 cursor buat banyak query
        # self.cursor = self.conn.cursor() 
    
    def connect_mongodb(self, conn_name, dir_path):
        credentials = self.read_json_file(dir_path + '/db_config.json')[conn_name]
        username = credentials['username']
        password = credentials['password']
        db_name = credentials['database']
        port = int(credentials['port'])
        host = credentials['host']
        
        print('------------')
        print(username)
        print(password)
        print(db_name) 
        print('------------')
        
        if username != '':
            uri = f"mongodb://{username}:{password}@{host}:{port}/{db_name}"
        else:
            uri = f"mongodb://{host}:{port}/{db_name}"

        conn_client = pymongo.MongoClient(uri)
        db_mongo = conn_client[db_name]
        return db_mongo

    def read_json_file(self, file_name):
        f = open(file_name)
        file_content = json.load(f)
        f.close()
        return file_content
    
    def upsert_dummy_data(self, engine_type, input):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]

        dummy_entry = input

        try:
            result = tbl_mongo_ai.find_one_and_update(
                {"identifier_field": dummy_entry.get("identifier_field", "default_value")},  # Replace with appropriate identifier field
                {"$set": dummy_entry},
                upsert=True
            )
            return "Success" if result else "No changes made"
        except Exception as e:
            print(f"message: {str(e)}")
            return str(e)
        
    def save_user_session(self, user_id, room_id):
        session_data = {
            "user_id": user_id,
            "room_id": room_id,
            "timestamp": datetime.datetime.now()
        }
        try:
            self.db_ai_mongo["user_sessions"].insert_one(session_data)
            return "Success"
        except Exception as e:
            print(f"Error saving session: {str(e)}")
            return str(e)
