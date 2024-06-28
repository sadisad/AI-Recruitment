from openai import OpenAI
import pandas as pd

# bagaimana caranya untuk melakukan edit pada BPJS kesehatan 1% di bayarkan karyawan, di edit menjadi 2% dibayarka karyawan, karna karyawan tersebut menanggung BPJS orang Tuanya
# Bagaimana jika ada mutasi company yang dilakukan tidak sesuai dengan Cut off nya?
# Mengapa pdf salary slip yang dikirim melalui ess mobile tidak terkirim ke email?

f = open("prompt_intro.txt", "r")
intro = f.read()
f.close()
f = open("sample_transkrip.txt", "r")
transkrip = f.read()
f.close()

input_prompt = intro.replace('<<< Transkrip >>>', transkrip)

client = OpenAI(api_key='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')
completion = client.chat.completions.create(
  model="gpt-4",
  messages=[{"role": "user", "content": input_prompt}
  ]
)

result = (completion.choices[0].message.content).split('--- Field Separator ---')
list_question, list_answer = [], []

for i in result:
    question_section = i.split('\n')
    for j in question_section:
        if 'Question : ' in j:
            list_question.append(j.replace('Question :', '').strip())
        
        if 'Jawaban : ' in j:
            list_answer.append(j.replace('Jawaban :', '').strip())

df = pd.DataFrame({'Question': list_question,
                          'Answer': list_answer})
 
datatoexcel = pd.ExcelWriter('Manual Knowledge.xlsx')
df.to_excel(datatoexcel, sheet_name='Knowledge')
datatoexcel.close()

print('Knowlegde Written Successfully.')