
from datetime import date, datetime
import fitz, os, names
from docx import Document

class FileHandler:
    
    def __init__(self):
        self.dir_logs = 'operational_files/Logs/'

    def save_chat_transcript(self, dict_session):
        today = date.today().strftime("%d-%m-%Y")
        file_path = self.dir_logs + today + '/' + dict_session['gpt_api_type'] + '.txt'

        try:
            os.mkdir(self.dir_logs + today)
        except:
            pass
        
        counter = 0
        with open(file_path, 'w', encoding="utf-8") as transcript_file:
            for entry in dict_session['history']:
                transcript_file.write(f"{entry['role']}: {entry['content']}\n")
                if entry['role'] != 'user' and dict_session['bool_chat']:
                    transcript_file.write(dict_session['usage'][counter] + '\n----------------\n')
                    counter += 1
            
            if dict_session['bool_chat'] == False:
                transcript_file.write(dict_session['usage'][counter] + '\n----------------\n')

        f = open(file_path, "r", encoding="utf-8")
        file_content = f.read()
        f.close()

        return file_content

# file_handler = FileHandler()
# file_handler.convert_all_cv_to_string()
# file_handler.save_chat_transcript