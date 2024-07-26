import os
import json
from groq import Groq
from gtts import gTTS
from modules.db_module.db import Database
import playsound

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

# Proses transkripsi audio menjadi teks
with open(filename, "rb") as file:
    transcription = client_whisper.audio.transcriptions.create(
        file=(filename, file.read()),
        model=config_whisper['model']
    )

# Cetak hasil transkripsi
transcribed_text = transcription.text
transcribed_text += 'Jawablah dengan bahasa indonesia'
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
output_audio_path = os.path.join(os.path.dirname(__file__), 'operational_files', 'Text_to_speech', 'response_2.mp3')
tts.save(output_audio_path)

# Memutar audio yang dihasilkan
playsound.playsound(output_audio_path)

# Simpan interaksi ke database
db = Database()
db.save_interaction(transcribed_text, response_text)
