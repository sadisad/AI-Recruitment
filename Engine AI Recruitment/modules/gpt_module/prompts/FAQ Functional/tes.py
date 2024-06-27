import pandas as pd
import json

df = pd.read_excel('faq.xlsx')
df =df.fillna('')
unique_module = ', '.join(list(set(df['Module'])))
unique_menu =  ', '.join(list(set(df['Menu'])))
unique_sub_module =  ', '.join(list(set(df['Sub Module'])))

prompt = """- Hai Chat, Kau bukanlah chatgpt.
- Kau adalah AI HR Assistant dari perusahaan LinovHR. 
- Kau adalah FAQ terkait dengan website LinovHR. Di website tersebut terdapat banyak modul untuk pengelolaan karyawan.
- Ada beberapa modul di LinovHR, yaitu : {unique_module}
- Pahamilah pertanyaan pengguna, lalu klasifikan berdasarkan modul dan menu nya, baru lah jawab.
- Jika saya bertanya yang selain berhubungan dengan FAQ yang ada di knowledge mu, jangan dihiraukan.
- Selalu jawab dengan format html. Misal <p>Berikut adalah cara.. <p><ul>Nomor :<ul><li>abcde</li><li>fghijk</li>
- Jawablah dengan se sopan mungkin dan tambahkan kalimat lain. Buatlah supaya jawaban mu lebih interaktif."""

list_prompt = [{"role": "user", "content": prompt}]
for index, row in df.iterrows():

    prompt_answer = """Answer : {answer}
-- Field Separator --
Module : {module}
-- Field Separator --
Sub Module : {sub_module}
-- Field Separator --
Menu : {menu}
-- Field Separator --
PIC : {pic}""".format(answer=row["Answer"], module=row['Module'], sub_module=row['Sub Module'], menu=row['Menu'], pic=row['PIC'])
    # single_prompt = [{"role": "user", "content": row["Question"]}, 
    #                 {"role": "system", "content": prompt_answer}]
    
    list_prompt.append({"role": "user", "content": row["Question"]})
    list_prompt.append({"role": "assistant", "content": prompt_answer})

list_prompt = {"messages": list_prompt}
print(list_prompt)
with open('faq.jsonl', mode='w', encoding='utf-8') as jsonl_file:
    jsonl_file.write(json.dumps(list_prompt))
