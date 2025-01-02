import pyodbc, json, uuid, os, pymongo, inflection
from datetime import date, datetime
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from sqlalchemy.engine import URL
from pymongo.errors import WriteError, OperationFailure
from pymongo import ReturnDocument
import pandas as pd
import random

class DatabaseOperations:
    def __init__(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.session_types = self.read_json_file(dir_path + '/schema_info.json')
        self.db_ai_mongo = self.connect_mongodb('mongo_db_ai', dir_path)
        
        self.file_path = os.path.join(os.getcwd(), 'modules', 'gpt_module', 'prompts', 'FAQ Functional', 'faq.xlsx')
        ### Jangan pernah cursor di atas begini, bikin cursor, langsung close tiap query. Jgn 1 cursor buat banyak query
        # self.cursor = self.conn.cursor() 
    
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
            tbl_mongo_ai = self.db_ai_mongo[table_name]
        except Exception as e:
            print('Error upsert to_db_mongo :' + str(e))
            return str(e)
        
        final_dict = {**{"last_updated" : last_updated}, **dict_result}
        final_dict = {key.replace('.', ','): value for key, value in final_dict.items()} ## MongoDB gabisa pake . di key nya

        if id_kolom != '':
            final_dict['_id'] = final_dict[id_kolom]
            del final_dict[id_kolom]
        
        row_id = self.mongo_upsert_exception(checker_upsert, final_dict, tbl_mongo_ai)
        # self.mongo_upsert_exception(checker_upsert, log_file_content, tbl_mongo_log)
        return row_id

    def mongo_upsert_exception(self, checker_upsert, final_dict, mongo_table):
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

# ---------------------------------- Popular question & list pertanyaan di welcoming chat --------------------------------
    
    def read_excel_file(self, file_path, sheet_name='FAQ'):
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            # print(f"Excel file read successfully from sheet '{sheet_name}': {df.head()}")  # Log the first few rows
            return df
        except Exception as e:
            print(f"Error reading Excel file: {str(e)}")
            return None
        
    def get_questions_by_module(self, module):
        file_path = self.file_path
        df = self.read_excel_file(file_path)
        if df is not None:
            filtered_df = df[df['Module'].str.contains(module, case=False, na=False)]
            return filtered_df.to_dict(orient='records')
        else:
            return {"error": "Failed to read the Excel file"}
        
    def get_faqs(self):
        file_path = self.file_path
        df = self.read_excel_file(file_path)
        if df is not None:
            faqs_df = df[['Question', 'Answer']]
            return faqs_df.to_dict(orient='records')
        else:
            return {"error": "Failed to read the Excel file"}
        
    def get_random_questions(self):
        file_path = self.file_path
        df = self.read_excel_file(file_path, sheet_name='FAQ')
        if df is not None:
            modules = df['Module'].unique()
            random_questions = []

            for module in modules:
                questions = df[df['Module'] == module].sample(n=1)
                random_questions.extend(questions.to_dict(orient='records'))
            
            formatted_questions = [{"Popular Question": question["Question"]} for question in random_questions]
            return formatted_questions
        else:
            return {"error": "Failed to read the Excel file"}

    def update_question_rating(self, question, rating_change):
        file_path = self.file_path
        df = self.read_excel_file(file_path, sheet_name='FAQ')
        if df is not None:
            if 'Rating' not in df.columns:
                df['Rating'] = 0
            
            idx = df[df['Question'] == question].index
            if not idx.empty:
                df.at[idx[0], 'Rating'] += rating_change
                df.to_excel(file_path, sheet_name='FAQ', index=False)
                return {"message": "Rating updated successfully"}
            else:
                return {"error": "Question not found"}
        else:
            return {"error": "Failed to read the Excel file"}

    def get_popular_questions_by_module(self):
            file_path = self.file_path
            df = self.read_excel_file(file_path, sheet_name='FAQ')
            if df is not None:
                if 'Rating' not in df.columns:
                    df['Rating'] = 0
                    df.to_excel(file_path, sheet_name='FAQ', index=False)
                
                modules = df['Module'].unique()
                popular_questions = []

                for module in modules:
                    top_question = df[df['Module'] == module].sort_values(by='Rating', ascending=False).iloc[0]
                    popular_questions.append({
                        'Module': top_question['Module'],
                        'Popular Question': top_question['Question'],
                        'Rating': int(top_question['Rating'])  # Convert int64 to native Python int
                    })
                return popular_questions
            else:
                return {"error": "Failed to read the Excel file"}
            
    def get_popular_questions_sorted_by_rating(self):
        file_path = self.file_path
        df = self.read_excel_file(file_path, sheet_name='FAQ')
        if df is not None:
            if 'Rating' not in df.columns:
                df['Rating'] = 0
                df.to_excel(file_path, sheet_name='FAQ', index=False)

            # Sort the DataFrame by Rating in descending order
            df_sorted = df.sort_values(by='Rating', ascending=False)
            popular_questions = []

            for _, row in df_sorted.iterrows():
                popular_questions.append({
                    'Module': row['Module'],
                    'Popular Question': row['Question'],
                    'Rating': int(row['Rating'])  # Convert int64 to native Python int
                })
            return popular_questions
        else:
            return {"error": "Failed to read the Excel file"}
        
##### ========================================= FAQ MANUAL CHAT ========================================= #####

    def create_room_chat(self, engine_type, room_id, question_context, user_id, status, functional_id, user_name, user_avatar, tenant_name, platform, functional_avatar):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]
        
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        detail_room = {
            "question_context": question_context,
            "status": status,
            "user_id": user_id,
            "user_name": user_name,
            "functional_id": functional_id,
            "functional_avatar": functional_avatar,
            "last_updated": last_updated,
            "user_avatar": user_avatar,
            "tenant_name": tenant_name,
            "platform": platform
        }
        
        try:
            result = tbl_mongo_ai.update_one(
                {"room_id": room_id},
                {"$set": detail_room},
                upsert=True
            )
            return "Success" if result.modified_count or result.upserted_id else "No changes made"
        except Exception as e:
            print(f"MongoDB - Error in create_room_chat: {str(e)}")
            return str(e)
        
    def update_chat_status(self, engine_type, room_id, current_status, functional_id, functional_avatar):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]
        
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        changes = {
            "status": current_status,
            "functional_id": functional_id,
            "last_updated": last_updated,
            "functional_avatar": functional_avatar
        }
        
        try:
            result = tbl_mongo_ai.update_one(
                {'room_id': room_id},
                {'$set': changes}
            )
            return result.matched_count > 0
        except Exception as e:
            print(e)
            return False
        
    def update_end_chat(self, engine_type, room_id, current_status):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]
        
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        changes = {
            "status": current_status,
            "last_updated": last_updated
        }
        
        try:
            result = tbl_mongo_ai.update_one(
                {'room_id': room_id},
                {'$set': changes}
            )
            return result.matched_count > 0
        except Exception as e:
            print(e)
            return False

    def upsert_manual_chat(self, engine_type, room_id, message, role):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]

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
        
    def get_all_chats(self, functional_id=None):
        collection = self.db_ai_mongo['faq_manual_chat']
        try:
            cursor = collection.find()
            documents = list(cursor)
            
            for doc in documents:
                doc['_id'] = str(doc['_id'])
            
            # Tentukan urutan status
            status_order = {'On Going': 1, 'Waiting': 2, 'Ended': 3}

            # Urutkan dokumen berdasarkan status dan functional_id jika disediakan
            documents.sort(key=lambda x: (
                status_order.get(x.get('status'), 4),  # Urutkan berdasarkan status
                -1 if (x.get('status') == 'On Going' and functional_id and x.get('functional_id') == functional_id) else 1,  # Prioritaskan 'On Going' dengan functional_id yang sesuai
                x.get('functional_id', '')  # Urutkan berdasarkan functional_id jika tidak ada
            ))
            
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error": str(e)}

        
    def filter_by_status(self, status):
        collection = self.db_ai_mongo['faq_manual_chat']
        filters = {}
        if status:
            filters['status'] = status
        try:
            cursor = collection.find(filters)
            documents = list(cursor)
            for doc in documents:
                print(doc['_id'])
                doc['_id'] = str(doc['_id'])  # Convert ObjectId to string for JSON serialization
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error": str(e)}
        
    def search_by_name(self, name):
        collection = self.db_ai_mongo['faq_manual_chat']
        try:
            cursor = collection.find({
                "$or": [
                    {"user_name": {"$regex": name, "$options": "i"}},
                    {"tenant_name": {"$regex": name, "$options": "i"}}
                ]
            })
            documents = list(cursor)
            for doc in documents:
                doc['_id'] = str(doc['_id'])  # Convert ObjectId to string for JSON serialization
            return documents
        except Exception as e:
            print("MongoDB - Error:", str(e))
            return {"error": str(e)}
        
    def RateFuntional(self, engine_type, functional_id, room_id, rate, description):
        config = self.session_types[engine_type]
        table_name = config['table_name'].replace('dbo.', '')
        tbl_mongo_ai = self.db_ai_mongo[table_name]
        
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        feedback_entry = {
            "room_id": room_id,
            "rate": rate,
            "description": description,
            "last_updated": last_updated
        }
        
        try:
            # Check if the feedback field exists and is an array
            existing_record = tbl_mongo_ai.find_one({"functional_id": functional_id})
            if existing_record:
                if "feedback" in existing_record:
                    # If feedback is not an array, convert it to an array
                    if not isinstance(existing_record["feedback"], list):
                        tbl_mongo_ai.update_one(
                            {"functional_id": functional_id},
                            {"$set": {"feedback": [existing_record["feedback"]]}}
                        )
                else:
                    # Initialize feedback as an empty array
                    tbl_mongo_ai.update_one(
                        {"functional_id": functional_id},
                        {"$set": {"feedback": []}}
                    )
            
            # Push the new feedback entry to the feedback array
            result = tbl_mongo_ai.update_one(
                {"functional_id": functional_id},
                {"$push": {"feedback": feedback_entry}},
                upsert=True
            )
            return "Success" if result.modified_count or result.upserted_id else "No changes made"
        except Exception as e:
            print(f"MongoDB - Error in RateFuntional: {str(e)}")
            return str(e)
        
    def get_feedback_for_functional(self, functional_id):
        collection = self.db_ai_mongo['faq_functionals_feedback']
        try:
            feedbacks = collection.find({"functional_id": functional_id, "feedback": {"$exists": True}})
            feedback_list = []
            for feedback in feedbacks:
                feedback['_id'] = str(feedback['_id'])  # Convert ObjectId to string
                feedback_list.extend(feedback.get('feedback', []))
            return feedback_list
        except Exception as e:
            print("MongoDB - Error in get_feedback_for_functional:", str(e))
            return {"error": str(e)}
        
    def store_sentiment_analysis_result(self, functional_id, results):
        """
        Stores the sentiment analysis results into the MongoDB collection 'sentiment_analysis'.
        """
        try:
            config = self.session_types['FAQ SENTIMENT ANALYSIS']
            table_name = config['table_name'].replace('dbo.', '')
            tbl_mongo_ai = self.db_ai_mongo[table_name]
        except Exception as e:
            print('Error store_sentiment_analysis_result:' + str(e))
            return str(e)

        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        analysis_result = {
            "functional_id": functional_id,
            "results": results,
            "last_updated": last_updated
        }

        try:
            result = tbl_mongo_ai.update_one(
                {"functional_id": functional_id},
                {"$set": analysis_result},
                upsert=True
            )
            return "Success" if result.modified_count or result.upserted_id else "No changes made"
        except Exception as e:
            print(f"MongoDB - Error in store_sentiment_analysis_result: {str(e)}")
            return str(e)
        
    def get_chat_transcripts(self, room_id):
        try:
            chat_data = self.get_row_data({"room_id": room_id}, 'faq_manual_chat', all_row=False)
            if 'chat_transcripts' not in chat_data:
                return {"error": "Chat transcripts not found for the given room ID"}
            
            chat_transcripts = chat_data['chat_transcripts']
            
            return chat_transcripts
        except Exception as e:
            print(e)
            return {"error": str(e)}
        
    def store_evaluate_user_question(self, dict_form):
        try:
            # Fetching the configuration for 'USER QUESTION EVALUATION'
            config = self.session_types['USER QUESTION EVALUATION']
            table_name = config['table_name'].replace('dbo.', '')
            tbl_mongo_ai = self.db_ai_mongo[table_name]
        except Exception as e:
            print('Error in fetching configuration or accessing MongoDB collection: ' + str(e))
            return str(e)

        # Getting the current timestamp
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Preparing the document to be inserted/updated
        
        analysis_result = {
            "room_id": dict_form['room_id'],
            "conclusion": dict_form['conclusion'],
            "is_context_relevant": dict_form['is_context_relevant'],
            "is_valuable": dict_form['is_valuable'],
            "last_updated": last_updated
        }

        try:
            # Performing the upsert operation
            result = tbl_mongo_ai.update_one(
                {"room_id": dict_form['room_id']},
                {"$set": analysis_result},
                upsert=True
            )
            if result.modified_count:
                return "Success - Document updated"
            elif result.upserted_id:
                return "Success - Document inserted"
            else:
                return "No changes made"
        except Exception as e:
            print(f"MongoDB - Error in store_evaluate_user_question: {str(e)}")
            return str(e)