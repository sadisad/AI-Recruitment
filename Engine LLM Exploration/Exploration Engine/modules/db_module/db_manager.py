import pyodbc, json, uuid, os, pymongo
from datetime import date, datetime
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from sqlalchemy.engine import URL
from pymongo.errors import WriteError, OperationFailure

class DatabaseOperations:
    def __init__(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.session_types = self.read_json_file(dir_path + '\\schema_info.json')
        self.connect_sql_server( 'sql_server_test', dir_path)
        # self.db_ai_mongo = self.connect_mongodb('mongo_db_ai', dir_path)
        # self.db_log_mongo = self.connect_mongodb('mongo_db_chat_log', dir_path)
        ### Jangan pernah cursor di atas begini, bikin cursor, langsung close tiap query. Jgn 1 cursor buat banyak query
        # self.cursor = self.conn.cursor() 
    
    def connect_sql_server(self, conn_name, dir_path):
        credentials = self.read_json_file(dir_path + '\\db_config.json')[conn_name]
        username = credentials['username']
        password = credentials['password']
        db_name = credentials['database']
        port = str(credentials['port'])
        port_engine, port_pyodbc = '', ''

        if '-' in port == False:
            port_engine = ':' + port
            port_pyodbc = ',' + port

        server = credentials['host']

        """Server Dev SQL Server"""
        self.engine = create_engine("mssql+pyodbc://{username}:{password}@{server}{port}/{db_name}?driver=ODBC+Driver+17+for+SQL+Server"
                            .format(username=username, password=password, db_name=db_name, port=port_engine, server=server))
        
        self.conn = pyodbc.connect(
                        # "Driver={SQL Server Native Client 11.0};"
                        "DRIVER={ODBC Driver 17 for SQL Server};"
                        "Server="+server+";"
                        "Database="+db_name+port_pyodbc+";"
                        "uid="+username+";"
                        "pwd="+password+";"
                        "Trusted_Connetion=no;")
    
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

        conn_client = pymongo.MongoClient(uri)
        db_mongo = conn_client[db_name]
        return db_mongo

    def read_json_file(self, file_name):
        f = open(file_name)
        file_content = json.load(f)
        f.close()
        return file_content

    def langchain_connect_db(self):
        connect_url = URL.create(
            'mssql+pyodbc',
            username='devnms2',
            password='admin',
            host='localhost',
            database='FunctionalDB',
            query={"driver" : "ODBC Driver 17 for SQL Server"})

        input_db = SQLDatabase.from_uri(connect_url)
        # print(input_db)
        # print(input_db.dialect)
        # print(input_db.get_usable_table_names())
        return input_db
    
    def generate_upsert_query(self, session_type):

        if session_type in self.session_types:
            config = self.session_types[session_type]
            table_name = config['table_name']
            primary_key = config['columns'][0]
            other_columns = config['columns'][1:]
            all_columns = [primary_key] + other_columns

            # Columns for insertion.
            source_columns = "SELECT ? AS " + ", ? AS ".join(all_columns)
            match_condition = f"target.{primary_key} = source.{primary_key}"
            update_set = ", ".join([f"{col} = source.{col}" for col in other_columns])
            insert_columns = ", ".join(all_columns)
            values_placeholders = "source." + ", source.".join(all_columns)
        
            query = f'''MERGE INTO {table_name} AS target
            USING ({source_columns}) AS source
            ON ({match_condition})
            WHEN MATCHED THEN
                UPDATE SET {update_set}
            WHEN NOT MATCHED THEN
                INSERT ({insert_columns}) VALUES ({values_placeholders});
            '''
        else:
            query = 'No need to merge'
        
        return query

    def check_update_insert(self, table, check_values, dict_values):
        where_clause = ' AND '.join([f"{column} = ?" for column in check_values.keys()])
        check_query = f"SELECT * FROM {table} WHERE {where_clause}"
        
        cursor = self.conn.cursor() 
        cursor.execute(check_query, *check_values.values())
        row = cursor.fetchone()
        
        if row:
            # Row exists, prepare and execute the update query
            update_set_clause = ', '.join([f"{key} = ?" for key in dict_values.keys()])
            update_query = f"UPDATE {table} SET {update_set_clause} WHERE {where_clause}"

            all_params = list(dict_values.values()) + list(check_values.values())
            final_query, final_params = update_query, all_params
        else:
            # Row does not exist, prepare and execute the insert query
            columns = ', '.join(dict_values.keys())
            placeholders = ', '.join(['?' for _ in dict_values.values()])
            insert_query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            final_query, final_params = insert_query, list(dict_values.values())

        try:
            cursor.execute(final_query, final_params)
            self.conn.commit()
        except Exception as e:
            print('Error :', e)
        finally:
            if cursor is not None:
                cursor.close()

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
        
        self.mongo_upsert_exception(checker_upsert, final_dict, tbl_mongo_ai)
        self.mongo_upsert_exception(checker_upsert, log_file_content, tbl_mongo_log)

    def mongo_upsert_exception(self, checker_upsert, final_dict, mongo_table):
        try:
            mongo_table.update_one(checker_upsert, {"$set": final_dict}, upsert=True)
        except WriteError as e:
            # Check if the error code is 66 which relates to modifying immutable field '_id'
            if e.code == 66:
                del final_dict['_id']
                
                try:
                    mongo_table.update_one(checker_upsert, {"$set": final_dict}, upsert=True)
                except Exception as e:
                    print("MongoDB - Error :", str(e))

            else:
                print("MongoDB - Database WriteError:", e.details)

        except OperationFailure as e:
            print("MongoDB - Operation failed:", e.details)

        except Exception as e:
            print("MongoDB - Error :", str(e))
    
    def store_to_db(self, engine_type, chat_type, session_id, log_file_content, dict_data={}):
        last_updated = datetime.now()
        unique_identifier = str(uuid.uuid4()) if engine_type != 'Form Filler' else dict_data['Name']
        id_tbl_value = session_id + unique_identifier if (chat_type == False) else session_id
        log_file_content = {'chat_transcript' : log_file_content}

        if engine_type == 'One CV Reviewer':
            config = self.session_types[engine_type]
            table_name = config['table_name']
            primary_key = config['columns'][0]
            other_columns = config['columns'][1:]
            all_columns = [primary_key] + other_columns
            parameters = [session_id, last_updated] + [str(dict_data.get(column, '')) for column in list(dict_data.keys())]

            dict_result = {}
            check_values = {
                'job_title': dict_data['Job Title'],
                'candidate_name': dict_data['Name']
            }

            count = 0
            for col in all_columns:
                dict_result[col] = parameters[count]
                count += 1

            # self.upsert_to_db_mongo(check_values, engine_type, last_updated, dict_result, log_file_content=log_file_content, id_kolom=primary_key)
            self.check_update_insert(table_name, check_values, dict_result)
        else:
            cursor = self.conn.cursor()
            query = self.generate_upsert_query(engine_type)

            if query != 'No need to merge' :
                # self.upsert_to_db_mongo({"_id": id_tbl_value}, engine_type, last_updated, dict_data, log_file_content=log_file_content)
                parameters = [id_tbl_value, last_updated] + [str(dict_data.get(column, '')) for column in list(dict_data.keys())]
                                
                try:
                    cursor.execute(query, parameters)
                    self.conn.commit()
                except Exception as e:
                    print('Error :', e)
                finally:
                    if cursor is not None:
                        cursor.close()

    def get_job_vacancy(self, job_title):
        cursor = self.conn.cursor() 
        table_name, column_name = 'dbo.job_vacancy', 'job_title'
        query = f"SELECT * FROM {table_name} WHERE LOWER({column_name}) = LOWER(?)"
        cursor.execute(query, [job_title])
        
        row = cursor.fetchone()
    
        if row:
            row = {cursor.description[i][0]: value for i, value in enumerate(row)}
            job_id, job_title = row['job_id'], row['job_title']
            job_vacancy = 'Job Yang Dilamar : ' + row['job_title'] + '\n'
            job_vacancy += 'Job Description : ' + row['job_desc'] + '\n'
            job_vacancy += 'Job Requirement : ' + row['job_requirement'] + '\n'
            job_vacancy += row['additional_notes']
            
        else:
            job_id, job_title, job_vacancy = 0, '', ''

        self.conn.commit()
        cursor.close()

        return job_id, job_title, job_vacancy

# db_ops = DatabaseOperations()
# print(db_ops.get_job_vacancy('AI enGIneer'))
# db_ops.store_to_db('Interview', 'Interview_ID_DUMMY', {"AAA" : "Hello World!"})
# db_ops.store_to_db('Form Filler', 'Form Filler_ID_DUMMY',
#                    {'Nama' : 'Ethan Hunt', 
#                      'Current Job Title' : 'IMF Agent', 
#                      'Summary' : 'A Legend', 
#                      'Phone Number' : '08172731233', 
#                      'Birth Of Date' : '-', 
#                      'Address' : '-',
#                     'Email' : '-', 
#                     'Experiences' : '5 Years', 
#                     'Educations' : 'IMF', 
#                     'Projects/Portfolios' : 'Ghost Protocol', 
#                     'Certifications' : 'Black Belt',
#                     'Awards' : 'Best Agent IMF', 
#                     'Publications' : '-', 
#                     'Volunteers' : '-', 
#                     'Languages' : 'All'})
# db_ops.store_to_db('CV Ranker', 'CV Ranker_ID_DUMMY',
#                    {'Job Title' : 'Artis', 
#                      'Job Requirement' : 'Populer', 
#                      'RANK 1' : 'Al', 
#                      'RANK 2' : 'El', 
#                      'RANK 3' : 'Dul', 
#                      'RANK LAINNYA' : 'Dhani'})
# db_ops.store_to_db('Redflags', 'Redflags_ID_DUMMY',
#                     {'Name' : 'Redflags Dummy', 
#                      'Employment Overlap' : 'Safe', 
#                      'Employment Gap' : 'Red Flag', 
#                      'High Turnover' : 'Safe', 
#                      'Non-Progressive Career Path' : 'Red Flag', 
#                      'Inconsistent Career Path' : 'Red Flag',
#                      'Absence of Organization Activity' : 'Safe', 
#                      'Absence of Endorsement/Reference' : 'Safe'
#                     })
       