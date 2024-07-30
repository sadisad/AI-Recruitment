import os
import json
import speech_recognition as sr
from groq import Groq
from gtts import gTTS
from Engine_Virtual_Assistant.modules.db_module.db_manager import Database
import playsound
from pydub import AudioSegment
from pydub.playback import play

# Perbarui jalur ke file konfigurasi LLM dan Whisper
config_llm_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'groq_config_llm.json')
config_whisper_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'groq_config_whisper.json')

# Memuat file konfigurasi LLM
with open(config_llm_path, 'r') as config_file:
    config_llm = json.load(config_file)

# Memuat file konfigurasi Whisper
with open(config_whisper_path, 'r') as config_file:
    config_whisper = json.load(config_file)

# Menginisialisasi klien Groq dengan API key dari konfigurasi LLM
client_llm = Groq(api_key=config_llm['api_key'])

# Menginisialisasi klien Groq dengan API key dari konfigurasi Whisper
client_whisper = Groq(api_key=config_whisper['api_key'])

# File audio yang akan diproses
filename = os.path.join(os.path.dirname(__file__), 'operational_files', 'Speech_to_text', 'Kenapa Pelajar Indonesia Suka Malu Bertanya_ (mp3cut.net).mp3')

# Fungsi untuk mengambil input dari mikrofon
def get_audio_from_mic():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Silakan berbicara...")
        audio = recognizer.listen(source)
        print("Mendapatkan audio...")
    try:
        text = recognizer.recognize_google(audio, language='id-ID')
        print(f"Teks yang dikenali: {text}")
        return text
    except sr.UnknownValueError:
        print("Google Speech Recognition tidak bisa mengenali audio")
        return ""
    except sr.RequestError as e:
        print(f"Tidak bisa meminta hasil dari Google Speech Recognition; {e}")
        return ""

# Mendapatkan input dari mikrofon
transcribed_text = get_audio_from_mic()

# Jika tidak ada input dari mikrofon, keluar dari program
if not transcribed_text:
    print("Tidak ada input dari mikrofon.")
    exit()

########################### DARI AUDIO/VIDEO FILE
# Proses transkripsi audio menjadi teks
# with open(filename, "rb") as file:
#     transcription = client_whisper.audio.transcriptions.create(
#         file=(filename, file.read()),
#         model=config_whisper['model']
#     )

# Cetak hasil transkripsi
# transcribed_text = transcription.text

transcribed_text += '\n Jawablah dengan bahasa indonesia'
print(f"Transcribed Text: {transcribed_text}")

# Menghasilkan respons dari LLM berdasarkan teks transkripsi
chat_completion = client_llm.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": transcribed_text
        }
    ],
    model=config_llm['model'],
)

# Cetak respons dari LLM
response_text = chat_completion.choices[0].message.content
print(f"Response: {response_text}")

# Menggunakan GTTS untuk mengonversi teks ke audio
tts = gTTS(text=response_text, lang='id')
output_audio_path = os.path.join(os.path.dirname(__file__), 'operational_files', 'Text_to_speech', 'response_3.mp3')
tts.save(output_audio_path)

# Memutar audio yang dihasilkan
playsound.playsound(output_audio_path)

# Simpan interaksi ke database
db = Database()
db.save_interaction(transcribed_text, response_text)
