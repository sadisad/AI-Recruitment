from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from sqlalchemy.engine import URL
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
import os

os.environ["OPENAI_API_KEY"] ='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'

connect_url = URL.create(
    'mssql+pyodbc',
    username='devnms2',
    password='admin',
    host='localhost',
    database='FunctionalDB',
    query={"driver" : "ODBC Driver 17 for SQL Server"})

input_db = SQLDatabase.from_uri(connect_url)
llm = ChatOpenAI(temperature=0, model_name='gpt-4')
db_chain = SQLDatabaseChain.from_llm(
    llm, 
    input_db, 
    verbose=True, 
    return_intermediate_steps=True,
    prompt=PromptTemplate(
        input_variables=['input', 'table_info', 'top_k'],
        template="""Anda seorang ahli MS SQL. 
        Diberikan sebuah pertanyaan, pertama-tama buatlah kueri MS SQL yang sintaksnya benar untuk dijalankan, kemudian lihat hasil dari kueri tersebut dan kembalikan jawaban untuk pertanyaan yang diberikan.
        Anda dapat mengurutkan hasil untuk mengembalikan data yang paling informatif di dalam database.
        Jawablah dengan se sopan mungkin dan tambahkan kalimat tambahan lain, seperti sapaan dan kata interaktif.

        \n\nGunakan format berikut:\n\n
        Pertanyaan: Pertanyaan di sini\n
        SQLQuery: Kueri SQL untuk dijalankan\n
        SQLResult: Hasil dari SQLQuery\n
        Jawaban: Jawaban akhir di sini\n\n
        Hanya gunakan tabel-tabel berikut:\n{table_info}\n\n
        Pertanyaan: {input}"""
    )
)

# print(db_chain)
answer_query = db_chain("Cara bikin approval gimana yak?")
import json
# print(json.dumps(answer_query))
# print('-------------')
print({"answer" : answer_query['result'], "sql_query" : answer_query['intermediate_steps'][1]})
# print('--------------')