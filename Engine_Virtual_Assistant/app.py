from flask import session
import pyaudio
import wave
import json
from datetime import datetime
import sys
import os
import time
from groq import Groq
import requests
import pyttsx3
import speech_recognition as sr

from gtts import gTTS
from pydub import AudioSegment
from modules.ai_module.llm import LanguageModel

from modules.db_module.db_manager import DatabaseOperations

db_ops = DatabaseOperations()

# Memuat konfigurasi dari groq_config_llm.json
config_llm_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'groq_config_llm.json')
ai_engine = LanguageModel()

# Inisialisasi Text-to-Speech engine
tts_engine = pyttsx3.init()

# Fungsi untuk menginisialisasi sesi dan mendapatkan user_id dan room_id
def initialize_session():
    response = requests.post('http://127.0.0.1:5000/virtual_assistant/initialize')
    
    if response.status_code == 200:
        data = response.json()
        
        print(data['llm_response'])
        
        return data['user_id'], data['room_id'], data['llm_response']
    else:
        print("Failed to initialize session")
        return None, None, None

# Fungsi untuk mengubah teks menjadi suara
def text_to_speech(text):
    tts = gTTS(text=text, lang='id')
    mp3_filename = "speech.mp3"
    wav_filename = "speech.wav"
    tts.save(mp3_filename)

    # Konversi file mp3 ke wav menggunakan pydub
    AudioSegment.from_mp3(mp3_filename).export(wav_filename, format="wav")

    # Memainkan file wav
    chunk = 1024
    wf = wave.open(wav_filename, 'rb')
    p = pyaudio.PyAudio()

    # Open stream
    stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True)

    # Read data in chunks and play
    data = wf.readframes(chunk)
    while data:
        stream.write(data)
        data = wf.readframes(chunk)

    # Stop and close stream
    stream.stop_stream()
    stream.close()

    # Close PyAudio
    p.terminate()
    wf.close()

    # Remove the files after playing

# Fungsi untuk merekam suara pengguna dan mengkonversinya menjadi teks
def record_and_transcribe():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Silakan bicara...")
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)
            print("Rekaman selesai.")
            transcribed_text = recognizer.recognize_google(audio, language="id-ID")
            print(f"Transcribed Text: {transcribed_text}")
            return transcribed_text
        except sr.WaitTimeoutError:
            print("Tidak ada suara yang terdeteksi dalam 10 detik, penghentian otomatis.")
            return ""
        except sr.UnknownValueError:
            print("Google Speech Recognition tidak dapat mengenali audio")
            return ""
        except sr.RequestError as e:
            print(f"Could not request results from Google Speech Recognition service; {e}")
            return ""

# Fungsi untuk mengotomatisasi interaksi dengan LLM
def automate_interaction(user_id, room_id, llm_response):
    keep_talking = True
    session_data = {"history": [{"role": "system", "content": llm_response}], "bool_chat": False}
    ai_engine.initialize_api_type('Virtual Assistant', session_data)

    while keep_talking:
        user_response = record_and_transcribe()
        
        db_ops.upsert_conversation_transcript(room_id, user_response, 'User')
        
        if user_response.strip() == "":
            keep_talking = False
            print("Penghentian interaksi karena tidak ada jawaban.")
            break
        
        session_data['history'].append({"role": "user", "content": user_response})
        
        # Send transcribed text to AI engine to get a response
        ai_response = ai_engine.generate_response(session_data=session_data)
        
        # Update the session history
        session_data['history'].append({"role": "system", "content": ai_response})
        
        db_ops.upsert_conversation_transcript(room_id, ai_response, 'AI')
        
        # Print AI response
        print(f"AI Response: {ai_response}")
        
        # Convert AI response to speech and play
        text_to_speech(ai_response)
        
        # # Save interaction to database
        # result = {
        #     "user_id": user_id,
        #     "room_id": room_id,
        #     "user_response": user_response,
        #     "ai_response": ai_response
        # }
        # try:
        #     response = requests.post('http://127.0.0.1:5000/virtual_assistant/test', json=result)
        #     response.raise_for_status()
        #     print(f"Response: {response.json()}")
        # except requests.exceptions.RequestException as e:
        #     print(f"Error sending request: {e}")

# Initialize session
user_id, room_id, llm_response = initialize_session()
text_to_speech(llm_response)

if user_id and room_id:
    automate_interaction(user_id, room_id, llm_response)