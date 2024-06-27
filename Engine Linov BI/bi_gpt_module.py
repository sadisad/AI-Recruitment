import json
from sqlalchemy import create_engine, MetaData
from llama_index.core import SQLDatabase, VectorStoreIndex, Settings
from llama_index.llms.groq import Groq
from llama_index.core.indices.struct_store.sql_query import SQLTableRetrieverQueryEngine
from llama_index.core.objects import SQLTableNodeMapping, ObjectIndex, SQLTableSchema
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

class bi_gpt_from_db:
    def __init__(self):
        ## GROQ CONFIG
        groq_config = self.read_config_file('config_groq.json')
        Settings.llm = Groq(model=groq_config['model'], api_key=groq_config['api_key'])
        Settings.embed_model = None
        
        ## DB CONFIG
        db_config = self.read_config_file('config_db.json')
        self.engine, self.connection = self.connect_to_postgre_db(db_config)
        self.define_db_metadata(self.engine, db_config['schema'])
        
    def read_config_file(self, file_name):
        f = open(file_name)
        data = json.load(f)
        f.close()
        return data
    
    def read_context_str(self, file_name):
        f = open('Context String Tables\\'+file_name, "r")
        context_str = f.read()
        f.close()
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
        
    def answer_question(self, question, table_name):
        # Construct table schema object
        table_schema_objs = [
            SQLTableSchema(
                table_name=table_name,
                context_str=self.read_context_str(table_name + '.txt')
            )
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

        # print(type(response.get_formatted_sources))
        # print(str(response.get_formatted_sources))
        if 'Error: Statement' in str(response.get_formatted_sources) and 'invalid SQL' in str(response.get_formatted_sources) :
            str_query_error = question + '\nThis Query is Error :\n' + str(response.metadata['sql_query'])
            str_query_error += '\n\nPlease Answer the question, and fix the query. And answer the question, without saying the fixed query.'
            str_query_error += '\nREMOVE THE FIXED QUERY FROM YOUR ANSWER' * 3
            response = query_engine.query(str_query_error)
            
        return {"question" : question, "answer" : response.response, "generated_query" : response.metadata['sql_query'].replace('\n', '')}