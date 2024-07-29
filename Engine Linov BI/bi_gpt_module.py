import json
import os
import time
import requests
from sqlalchemy import create_engine, MetaData
from llama_index.core import SQLDatabase, VectorStoreIndex, Settings
from llama_index.llms.groq import Groq
from llama_index.core.indices.struct_store.sql_query import SQLTableRetrieverQueryEngine
from llama_index.core.objects import SQLTableNodeMapping, ObjectIndex, SQLTableSchema
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import re
import openai
from nltk.corpus import stopwords

class bi_gpt_from_db:
    def __init__(self):
        # self.dir_path = os.path.dirname(os.path.realpath(__file__))
        
        ## GROQ CONFIG
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        credentials = self.read_config_file('gpt_config.json')
        self.api_key, self.session_faq, openai.api_key = credentials['api_key'], {}, credentials['api_key']
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.indonesian_stopwords = stopwords.words('indonesian')
        self.response_config = {"model": credentials['model'],
                "temperature": credentials['temperature'],
                "top_p": credentials['top_p'],
                "frequency_penalty": credentials['frequency_penalty'],
                "presence_penalty": credentials['presence_penalty']}
        
        ## DB CONFIG
        db_config = self.read_config_file('config_db.json')
        self.engine, self.connection = self.connect_to_postgre_db(db_config)
        self.define_db_metadata(self.engine, db_config['schema'])
        
        ## Preprocess table descriptions
        self.table_descriptions = self.preprocess_table_descriptions('Context String Tables/all tables.txt')
        print("Table Descriptions Loaded:")
        for table, desc in self.table_descriptions.items():
            print(f"Table: {table}, Description: {desc}")
    
    def read_config_file(self, file_name):
        with open(file_name, 'r') as f:
            data = json.load(f)
        return data
    
    def read_context_str(self, file_name):
        with open(f'Context String Tables/{file_name}', 'r') as f:
            context_str = f.read()
        return context_str
    
    def connect_to_postgre_db(self, db_config):
        username = db_config['username']
        password = db_config['password']
        host = db_config['host']
        port = db_config['port']
        database_name = db_config['database_name']
        schema = db_config['schema']

        # Connection string
        connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database_name}"

        # Connect to the database
        engine = create_engine(connection_string)

        try:
            connection = engine.connect()
        except Exception as e:
            print(f"Connection failed: {e}")
            
        return engine, connection
    
    def define_db_metadata(self, engine, schema):
        self.metadata_obj = MetaData()
        self.metadata_obj.reflect(engine, schema=schema)
        self.sql_database = SQLDatabase(engine, schema=schema)
        self.table_node_mapping = SQLTableNodeMapping(self.sql_database)
        
    def preprocess_table_descriptions(self, file_path):
        with open(file_path, 'r') as file:
            lines = file.readlines()
        
        table_descriptions = {}
        current_table = None
        description = []

        for line in lines:
            if line.strip() == "===============================":
                if current_table and description:
                    table_descriptions[current_table] = ' '.join(description)
                current_table = None
                description = []
            elif line.startswith("The '") and line.endswith("' table stores information about"):
                current_table = re.findall(r"'(.*?)'", line)[0]
            elif current_table:
                description.append(line.strip())
        
        if current_table and description:
            table_descriptions[current_table] = ' '.join(description)
        
        return table_descriptions
    
    def identify_relevant_tables(self, question):
        relevant_tables = []
        for table, description in self.table_descriptions.items():
            print(f"Checking table: {table}")
            if any(keyword.lower() in description.lower() for keyword in question.split()):
                print(f"Found relevant table: {table}")
                relevant_tables.append(table)
        return relevant_tables
    
    def read_intro_prompt(self, file_name):
        f = open(self.dir_path + '\\' + file_name, "r", encoding="utf8")
        str_prompt = f.read()
        f.close()
        return str_prompt
    
    ############################################
    def initialize_relevant_tables(self, question):
        introductory = self.read_intro_prompt('prompt\\intro_prompt.txt')
        tables = introductory.replace('<-> Form Fields <->', 
                                      self.read_intro_prompt('Context String Tables\\all tables.txt'))
        
        prompt = tables.replace('<-> Question Fields <->', question)
        
        return prompt
    
    # def hit_groq_api(self, session, one_time_message=''):
    #     response = self.groq_client.complete(
    #         prompt=one_time_message
    #     )

    #     json_response = json.loads(response.json())
        
    #     try:
    #         answer = json_response.get("choices")[0].get("message")["content"]
    #     except:
    #         answer = 'Maaf, saya mengalami kesalahan. Bisa diulang kembali?'
        
    #     return answer, json_response
    
    def extract_table_names(self, answer):
        lines = answer.strip().split('\n')
        table_names = [line for line in lines if line.startswith('fact_')]
        return set(table_names)
    def hit_openai_api(self, session, one_time_message=''):

        if one_time_message == '' :
            self.response_config['messages'] = session['history']
        else:
            self.response_config['messages'] = [{"role": "system", "content" : one_time_message}]

        try:
            response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)
        except:
            time.sleep(3)
            response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)

        for i in range(3):
            json_response = response.json()
            # print('<<< ' + session['gpt_api_type'] + ' >>>')
            print(json_response)
            print('==========')

            if 'error' in json_response:

                if 'please try again in' in json_response['error']['message'].lower():
                    print('Sleeping, Limit.')
                    print('==========')
                    time.sleep(int(i) * 10) # Handle Limit
                    response = requests.post(f"https://api.openai.com/v1/chat/completions", headers=self.headers, json=self.response_config)
                elif 'request too large for' in json_response['error']['message'].lower():
                    print('Limit, harus dihapus chat history nya.')
                    print('==========')
                    # answer = "Limit, harus dihapus chat history nya. To Be Fixed. Mungkin Chatnya Harus Dihapus."
                    answer = "Error, please contact administrator."
                    return answer, json_response
            else:
                break

        try:
            answer = json_response.get("choices")[0].get("message")["content"]
        except:
            answer = 'Maaf, saya mengalami kesalahan. Bisa diulang kembali?'
            
        table_names = self.extract_table_names(answer)
        
        return answer, json_response, table_names
    
    def answer_question(self, question, tables_names):
        relevant_tables = tables_names
        if not relevant_tables:
            return {"question": question, "answer": "No relevant tables found to answer the question."}
        
        # Construct table schema objects
        table_schema_objs = [
            SQLTableSchema(
                table_name=table,
                context_str=self.read_context_str(table + '.txt')
            )
            for table in relevant_tables
        ]

        # Create object index and query engine
        obj_index = ObjectIndex.from_objects(
            table_schema_objs,
            self.table_node_mapping,
            VectorStoreIndex,
        )

        query_engine = SQLTableRetrieverQueryEngine(
            self.sql_database, obj_index.as_retriever(similarity_top_k=1)
        )

        # Execute the query
        response = query_engine.query(question)

        if 'Error: Statement' in str(response.get_formatted_sources) and 'invalid SQL' in str(response.get_formatted_sources):
            str_query_error = question + '\nThis Query is Error :\n' + str(response.metadata['sql_query'])
            str_query_error += '\n\nPlease Answer the question, and fix the query. And answer the question, without saying the fixed query.'
            str_query_error += '\nREMOVE THE FIXED QUERY FROM YOUR ANSWER' * 3
            response = query_engine.query(str_query_error)
            
        return {"question": question, "answer": response.response, "generated_query": response.metadata['sql_query'].replace('\n', '')}
    
    ######################################################
    # def answer_question(self, question):
    #     relevant_tables = self.identify_relevant_tables(question)
    #     if not relevant_tables:
    #         return {"question": question, "answer": "No relevant tables found to answer the question."}
        
    #     # Construct table schema objects
    #     table_schema_objs = [
    #         SQLTableSchema(
    #             table_name=table,
    #             context_str=self.read_context_str(table + '.txt')
    #         )
    #         for table in relevant_tables
    #     ]

    #     # Create object index and query engine
    #     obj_index = ObjectIndex.from_objects(
    #         table_schema_objs,
    #         self.table_node_mapping,
    #         VectorStoreIndex,
    #     )

    #     query_engine = SQLTableRetrieverQueryEngine(
    #         self.sql_database, obj_index.as_retriever(similarity_top_k=1)
    #     )

    #     # Execute the query
    #     response = query_engine.query(question)

    #     if 'Error: Statement' in str(response.get_formatted_sources) and 'invalid SQL' in str(response.get_formatted_sources):
    #         str_query_error = question + '\nThis Query is Error :\n' + str(response.metadata['sql_query'])
    #         str_query_error += '\n\nPlease Answer the question, and fix the query. And answer the question, without saying the fixed query.'
    #         str_query_error += '\nREMOVE THE FIXED QUERY FROM YOUR ANSWER' * 3
    #         response = query_engine.query(str_query_error)
            
    #     return {"question": question, "answer": response.response, "generated_query": response.metadata['sql_query'].replace('\n', '')}
