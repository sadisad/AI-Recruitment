
from datetime import date, datetime
import fitz, os, names
from docx import Document

class FileHandler:

    def __init__(self):
        self.dir_logs = 'operational_files/Logs/'

        try :
            os.mkdir(self.dir_target)
        except:
            pass
    
    def save_chat_transcript(self, dict_session):
        today = date.today().strftime("%d-%m-%Y")
        current_time = datetime.now().strftime("%H-%M-%S") 
        file_path = os.path.join(self.dir_logs, today, f"{dict_session['gpt_api_type']}_{current_time}.txt")


        try:
            os.mkdir(self.dir_logs + today)
        except:
            pass
        
        counter = 0
        with open(file_path, 'w', encoding="utf-8") as transcript_file:
            for entry in dict_session['history']:
                transcript_file.write(f"{entry['role']}: {entry['content']}\n")
                if entry['role'] != 'user' and dict_session['bool_chat']:
                    counter += 1

        f = open(file_path, "r", encoding="utf-8")
        file_content = f.read()
        f.close()

        return file_content