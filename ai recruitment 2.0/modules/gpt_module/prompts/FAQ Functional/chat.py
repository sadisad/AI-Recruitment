# from langchain.chat_models import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from langchain.chains import create_sql_query_chain
from sqlalchemy.engine import URL
import os
from langchain.llms import OpenAI
from langchain_openai import ChatOpenAI
from operator import itemgetter
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool


os.environ["OPENAI_API_KEY"] ='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'

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
llm = ChatOpenAI(temperature=0)
print(llm.get_name)

answer_prompt = PromptTemplate.from_template(
    """Hai Chat, Kau bukanlah chatgpt.
Kau adalah AI HR Assistant dari perusahaan Lawencon. 
Kau berfungsi sebagai FAQ (Frequently Asked Question), untuk penggunaan website bernama LinovHR.
Segala sesuatu yang berhubungan dengan karyawan, dapat di lakukan di website LinovHR ini.
Website LinovHR memiliki banyak modul. Nama modul tersebut bisa diakses di kolom module.
Jika saya bertanya yang selain berhubungan dengan FAQ yang ada di tabel, jangan dihiraukan.
Hanya gunakan tabel dbo.faq_functional.
    Jangan menjawab kecuali jawaban nya ada di tabel dbo.faq_functional. Jangan mengada ngada.
    Tolong jawab pertanyaan pengguna dengan menggunakan pertanyaan yang diberikan sebelumnya, kueri SQL yang relevan, dan hasil SQL yang dihasilkan. 
    Jawablah dengan se sopan mungkin dan tambahkan kalimat tambahain lain. Buatlah supaya jawaban mu lebih interaktif.
    Jika kau tidak tau jawabannya, atau tidak ada query yang tepat. Jawablah '--- No Answer ---'.
    Jika kau tidak tau jawabannya, atau tidak ada query yang tepat. Jawablah '--- No Answer ---'.
    Jika pertanyaannya tidak ada di tabel atau di luar konteks. Jawablah '--- Out of Context ---'.

Pertanyaan : {question}
--- Field Separator ---
SQL Query : {query}
--- Field Separator ---
SQL Result : {result}
--- Field Separator ---
Jawaban : """
)

execute_query = QuerySQLDataBaseTool(db=input_db)
write_query = create_sql_query_chain(llm, input_db)

answer = answer_prompt | llm | StrOutputParser()
chain = (
    RunnablePassthrough.assign(query=write_query).assign(
        result=itemgetter("query") | execute_query
    )
    | answer
)

question = {"question": "Cara membuat approval gmn sih"}
response = chain.invoke(question)
query = write_query.invoke(question)
print(response)
print(query)