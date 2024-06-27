import pyodbc, json, uuid, os, pymongo, inflection
from datetime import date, datetime
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from sqlalchemy.engine import URL
from pymongo.errors import WriteError, OperationFailure
from pymongo import ReturnDocument

class DatabaseOperations:
    def __init__(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.session_types = self.read_json_file(dir_path + '\\schema_info.json')
        self.db_ai_mongo = self.connect_mongodb('mongo_db_ai', dir_path)
        self.db_log_mongo = self.connect_mongodb('mongo_db_chat_log', dir_path)
        ### Jangan pernah cursor di atas begini, bikin cursor, langsung close tiap query. Jgn 1 cursor buat banyak query
        # self.cursor = self.conn.cursor() 
    
    def connect_mongodb(self, conn_name, dir_path):
        credentials = self.read_json_file(dir_path + '\\db_config.json')[conn_name]
        username = credentials['username']
        password = credentials['password']
        db_name = credentials['database']
        port = int(credentials['port'])
        host = credentials['host']
        
        if username != '':
            uri = f"mongodb://{username}:{password}@{host}:{port}/{db_name}"
        else:
            uri = f"mongodb://{host}:{port}/{db_name}"
        
        print(uri)

        conn_client = pymongo.MongoClient(uri)
        db_mongo = conn_client[db_name]
        return db_mongo

    def read_json_file(self, file_name):
        f = open(file_name)
        file_content = json.load(f)
        f.close()
        return file_content
    
    def upsert_to_db_mongo(self, checker_upsert, engine_type, last_updated, dict_result, log_file_content={}, id_kolom=''):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]
        tbl_mongo_log = self.db_log_mongo[table_name]
        final_dict = {**{"last_updated" : last_updated}, **dict_result}
        final_dict = {key.replace('.', ','): value for key, value in final_dict.items()} ## MongoDB gabisa pake . di key nya

        if id_kolom != '':
            final_dict['_id'] = final_dict[id_kolom]
            del final_dict[id_kolom]
        
        row_id = self.mongo_upsert_exception(checker_upsert, final_dict, tbl_mongo_ai)
        # self.mongo_upsert_exception(checker_upsert, log_file_content, tbl_mongo_log)
        return row_id

    def mongo_upsert_exception(self, checker_upsert, final_dict, mongo_table):

        result = mongo_table.find_one_and_update(checker_upsert, {'$set': final_dict}, upsert=True, return_document=ReturnDocument.AFTER) 
        document_id = result['_id'] if result else None
        return document_id

        try:
            result = mongo_table.find_one_and_update(checker_upsert, {'$set': final_dict}, upsert=True, return_document=ReturnDocument.AFTER) 
            document_id = result['_id'] if result else None
            return document_id
        
        except Exception as e:
            # Check if the error code is 66 which relates to modifying immutable field '_id'
            if e.code == 66:
                del final_dict['_id']
                
                try:
                    result = mongo_table.find_one_and_update(checker_upsert, {'$set': final_dict}, upsert=True, return_document=ReturnDocument.AFTER) 
                    document_id = result['_id'] if result else None
                    return document_id
                except Exception as e:
                    print("MongoDB - Error :", str(e))

            else:
                print("MongoDB - Database WriteError:", e.details)

    
    def store_to_db(self, engine_type, chat_type, session_id, log_file_content, dict_data={}, id_dict={}):
        last_updated = datetime.now()
        # unique_identifier = str(uuid.uuid4()) if engine_type != 'Form Filler' else dict_data['Name']
        unique_identifier = str(uuid.uuid4())
        id_tbl_value = session_id + '_' + unique_identifier if (chat_type == False) else session_id
        log_file_content = {'chat_transcript' : log_file_content}

        row_id = self.upsert_to_db_mongo(id_dict, engine_type, last_updated, dict_data, log_file_content=log_file_content)

        return row_id
            

    def get_row_data(self, json_searcher, tbl_name, all_row=False):
        collection = self.db_ai_mongo[tbl_name]
        
        try:
            if all_row :
                cursor = collection.find()
                documents = list(cursor)
                return documents
            else:
                row = collection.find_one(json_searcher)
                if row:
                    row['_id'] = str(row['_id'])
                    return row
                else:
                    return {"message" : "Data not found"}
            
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error" : str(e)}
        
    def get_job_vacancy(self, job_id):
        tbl_job_vac = self.db_ai_mongo['job_vacancy']
        # job_title_lower = job_title.lower()
        # row = tbl_job_vac.find_one({'job_title': {'$regex': f'^{job_title_lower}$', '$options': 'i'}})

        row = tbl_job_vac.find_one({'job_id': job_id})

        if row:
            job_id = row.get('job_id', 0)
            job_title = row.get('job_title', '')
            job_vacancy = (
                'Job Yang Dilamar : ' + job_title + '\n' +
                'Role Overview : ' + row.get('role_overview', '') + '\n' +
                'Job Description : ' + row.get('responsibilities', '') + '\n' +
                'Job Requirement : ' + row.get('qualifications', '') + '\n' +
                row.get('additional_notes', '')
            )
            
            return job_id, job_title, job_vacancy
        else:
            return {"message" : "No row found."}