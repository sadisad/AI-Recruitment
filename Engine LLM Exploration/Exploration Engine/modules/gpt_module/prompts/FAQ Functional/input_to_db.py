import pyodbc, base64 

import pandas as pd

# Assuming df is your DataFrame after reading Excel
df = pd.read_excel('faq.xlsx')
df =df.fillna('')
server = 'localhost'
database = 'AI_GPT_HR'
username = 'devnms2'
password = 'admin'
cnxn = pyodbc.connect(
                        # "Driver={SQL Server Native Client 11.0};"
                        "DRIVER={ODBC Driver 17 for SQL Server};"
                        "Server="+server+";"
                        "Database="+database+";"
                        "uid="+username+";"
                        "pwd="+password+";"
                        "Trusted_Connection=no;"
                        'charset=UTF-8')

cursor = cnxn.cursor()

# Template for the MERGE statement
merge_query = """
MERGE INTO dbo.faq_functional AS target
USING (VALUES
       (?, ?, ?, ?, ?, ?)
      ) AS source (id_faq_functional, module, menu, question, answer, pic)
ON target.id_faq_functional = source.id_faq_functional
WHEN MATCHED THEN
    UPDATE SET target.module = source.module,
               target.menu = source.menu,
               target.question = source.question,
               target.answer = source.answer,
               target.pic = source.pic
WHEN NOT MATCHED THEN
    INSERT (id_faq_functional, module, menu, question, answer, pic)
    VALUES (source.id_faq_functional, source.module, source.menu, source.question, source.answer, source.pic);
"""

# Loop over the DataFrame rows
for index, row in df.iterrows():

    joined_str = row['Question'] + row['Answer']
    joined_str_byte = joined_str.encode('utf-8')
    base64_bytes = base64.b64encode(joined_str_byte) 
    base64_string = base64_bytes.decode("ascii") 

    values = (base64_string[:100], row['Module'], row['Menu'], row['Question'], row['Answer'], row['PIC'])
    cursor.execute(merge_query, values)

# Commit the transaction
cnxn.commit()

# Close the connection
cursor.close()
cnxn.close()
