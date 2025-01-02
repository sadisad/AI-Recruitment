import pyodbc, json, uuid, os, pymongo, inflection
from datetime import date, datetime
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from sqlalchemy.engine import URL
from pymongo.errors import WriteError, OperationFailure
from pymongo import ReturnDocument
import logging

class DatabaseOperations:
    def __init__(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.session_types = self.read_json_file(dir_path + '/schema_info.json')
        self.db_recruitment = self.connect_mongodb('mongo_db_recruitment', dir_path)
        ### Jangan pernah cursor di atas begini, bikin cursor, langsung close tiap query. Jgn 1 cursor buat banyak query
        # self.cursor = self.conn.cursor() 
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
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
        f = open(file_name)
        file_content = json.load(f)
        f.close()
        return file_content
    
    def upsert_to_db_mongo(self, checker_upsert, engine_type, last_updated, dict_result, log_file_content={}, id_kolom=''):
        try:
            config = self.session_types[engine_type]
            table_name = config['table_name'].replace('dbo.', '')
            tbl_mongo_ai = self.db_recruitment[table_name]
            final_dict = {**{"last_updated": last_updated}, **dict_result}
            final_dict = {key.replace('.', ','): value for key, value in final_dict.items()}  # MongoDB cannot use '.' in key names

            if id_kolom != '':
                final_dict['_id'] = final_dict[id_kolom]
                del final_dict[id_kolom]
            
            # Log before the upsert operation
            # self.logger.info(f"Upserting to MongoDB: Collection='{table_name}', Checker='{checker_upsert}', Data='{final_dict}'")

            row_id = self.mongo_upsert_exception(checker_upsert, final_dict, tbl_mongo_ai)

            # Log after the upsert operation
            # self.logger.info(f"Upsert completed successfully: RowID='{row_id}'")
            return row_id

        except Exception as e:
            # Log the exception
            # self.logger.error(f"Error during upsert_to_db_mongo: {str(e)}")
            raise  # Re-raise the exception for further handling

    def mongo_upsert_exception(self, checker_upsert, final_dict, mongo_table):

        result = mongo_table.find_one_and_update(checker_upsert, {'$set': final_dict}, upsert=True, return_document=ReturnDocument.AFTER) 
        document_id = result['_id'] if result else None
        return document_id
                
    def store_to_db(self, engine_type, chat_type, session_id, log_file_content, dict_data={}, id_dict={}):
        try:
            last_updated = datetime.now()
            unique_identifier = str(uuid.uuid4())
            id_tbl_value = session_id + '_' + unique_identifier if not chat_type else session_id
            log_file_content = {'chat_transcript': log_file_content}

            row_id = self.upsert_to_db_mongo(id_dict, engine_type, last_updated, dict_data, log_file_content=log_file_content)

            return row_id
        except Exception as e:
            print(f"Error in store_to_db for engine_type '{engine_type}': {str(e)}")
            raise

    def get_row_data(self, json_searcher, tbl_name, all_row=False):
        collection = self.db_recruitment[tbl_name]
        
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
        tbl_job_vac = self.db_recruitment['job_vacancy']

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
        
    def update_row_data(self, filter_criteria, update_data, collection_name):
        """
        Update documents in the specified MongoDB collection based on filter criteria.
        """
        try:
            collection = self.db_recruitment[collection_name]
            result = collection.update_one(filter_criteria, {'$set': update_data})
            return {'modified_count': result.modified_count}
        except Exception as e:
            print(f"Error updating row data: {e}")
            raise
        
    def get_all_extracted_cv(self):
        collection = self.db_recruitment['cv_form_filler']
        try:
            cursor = collection.find()
            documents = list(cursor)
            for doc in documents:
                doc['_id'] = str(doc['_id'])
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error" : str(e)}
    
    def insert_manual_candidate(self, candidate_data):
        try:
            collection = self.db_recruitment['manual_input_candidates']
            candidate_data['created_at'] = datetime.now()
            result = collection.insert_one(candidate_data)
            return result.inserted_id
        except Exception as e:
            print(f"Error inserting manual candidate: {e}")
            raise
        
    def get_candidate_profile_matching_result(self):
        collection = self.db_recruitment['candidate_profile_matching']
        try:
            cursor = collection.find()
            documents = list(cursor)
            for doc in documents:
                doc['_id'] = str(doc['_id'])
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error" : str(e)}
        
    def get_candidate_redflags(self):
        collection = self.db_recruitment['candidate_redflags']
        try:
            cursor = collection.find()
            documents = list(cursor)
            for doc in documents:
                doc['_id'] = str(doc['_id'])
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error" : str(e)}
        
    def upsert_interview_chats(self, engine_type, room_id, message, role):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_recruitment[table_name]

        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timestamp_key = last_updated.replace(':', '_').replace('-', '_').replace(' ', '_')

        chat_entry = {
            f"chat_transcripts.{timestamp_key}.role": role,
            f"chat_transcripts.{timestamp_key}.content": message,
            "last_updated": last_updated,
        }

        try:
            existing_record = tbl_mongo_ai.find_one({"room_id": room_id})

            if existing_record:
                result = tbl_mongo_ai.update_one(
                    {"room_id": room_id},
                    {"$set": chat_entry},
                    upsert=False
                )
                return "Success" if result.modified_count else "No changes made"
            else:
                return "Room ID not found in the database", 404
        except Exception as e:
            print(f"MongoDB - Error in upsert_manual_chat: {str(e)}")
            return str(e)
        
    def update_session_state(self, room_id, session_state):
        """
        Update the session state in the database.
        """
        try:
            # Insert or update the session state for a given room_id
            self.db_recruitment['session_states'].update_one(
                {'room_id': room_id},
                {'$set': session_state},
                upsert=True
            )
        except Exception as e:
            print(f"Error updating session state: {str(e)}")
            raise e

    def get_session_state(self, room_id):
        """
        Retrieve the session state from the database.
        """
        try:
            # Retrieve the session state for a given room_id
            return self.db_recruitment['session_states'].find_one({'room_id': room_id})
        except Exception as e:
            print(f"Error retrieving session state: {str(e)}")
            raise e
        
    def get_all_room_interview(self):
        collection = self.db_recruitment['interview_transcripts']
        try:
            cursor = collection.find()
            documents = list(cursor)
            for doc in documents:
                doc['_id'] = str(doc['_id'])
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error" : str(e)}
        
        
    def delete_row_data(self, filter_criteria, collection_name):
        """
        Menghapus satu dokumen berdasarkan kriteria filter dari koleksi yang ditentukan.
        """
        try:
            collection = self.db_recruitment[collection_name]
            result = collection.delete_one(filter_criteria)
            return result
        except Exception as e:
            print(f"Error deleting row data: {e}")
            raise

    def delete_all_data(self, collection_name):
        """
        Menghapus semua dokumen dari koleksi yang ditentukan.
        """
        try:
            collection = self.db_recruitment[collection_name]
            result = collection.delete_many({})
            return result
        except Exception as e:
            print(f"Error deleting all data: {e}")
            raise
        
    def delete_cv_data(self, cv_id):
        """
        Menghapus satu CV berdasarkan cv_id dari koleksi yang terkait.
        """
        try:
            filter_criteria = {'id_cv': cv_id}
            result_form_filler = self.delete_row_data(filter_criteria, 'cv_form_filler')
            result_cv_directories = self.delete_row_data(filter_criteria, 'cv_directories')
            result_candidate_profile_matching = self.delete_row_data(filter_criteria, 'candidate_profile_matching')
            result_candidate_redflags = self.delete_row_data(filter_criteria, 'candidate_redflags')

            return {
                'cv_form_filler_deleted': result_form_filler.deleted_count,
                'cv_directories_deleted': result_cv_directories.deleted_count,
                'candidate_profile_matching_deleted': result_candidate_profile_matching.deleted_count,
                'candidate_redflags_deleted': result_candidate_redflags.deleted_count,
            }
        except Exception as e:
            print(f"Error deleting CV data: {e}")
            raise