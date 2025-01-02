from datetime import date, datetime
import fitz, os, names
from docx import Document

class FileHandler:

    def __init__(self):
        self.folder_cv = 'operational_files/CV/'
        self.dir_source = self.folder_cv + 'Original CVs/'
        self.dir_target = self.folder_cv + 'CV Strings/'
        self.dir_logs = 'operational_files/Logs/'

        try :
            os.mkdir(self.dir_target)
        except:
            pass

    def str_to_txt(self, file_type, cv_file, str_result):
        file_flag = file_type + ' - '
        text_file = open(self.dir_target + file_flag + cv_file.replace('.'+file_type, '.txt'), "w", encoding="utf-8")
        text_file.write(str_result)
        text_file.close()
    
    def pdf_to_str(self, pdf_file):
        doc = fitz.open(self.dir_source + pdf_file)
        all_str = ''
        dummy_name = names.get_full_name()

        for page in doc:
            text = page.get_text().replace('IM A. SAMPLE', dummy_name)
            all_str += text

        all_str = all_str.replace('\n', '')
        return all_str
    
    def docx_to_str(self, docx_file):
        doc = Document(self.dir_source + docx_file)

        all_str = ''
        for paragraph in doc.paragraphs:
            all_str += paragraph.text
        all_str = all_str.replace('\n', '')
        return all_str

    def checker_and_generator(self, filename):
        if '.docx' in filename :
            file_type, str_result = 'docx', self.docx_to_str(filename)
        else:
            file_type, str_result = 'pdf', self.pdf_to_str(filename)
        
        return file_type, str_result
    
    def convert_all_cv_to_string(self):
        cv_files = os.listdir(self.dir_source)

        for cv in cv_files:
            file_type, str_result = self.checker_and_generator(cv)
            self.str_to_txt(file_type, cv, str_result)
    
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