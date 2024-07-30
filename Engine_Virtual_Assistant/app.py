import pyaudio
import wave
import json
from datetime import datetime
import sys
import os
from groq import Groq
import requests
import pyttsx3
import speech_recognition as sr

from gtts import gTTS
from pydub import AudioSegment
from modules.ai_module.llm import LanguageModel

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
    os.remove(mp3_filename)
    os.remove(wav_filename)

# Fungsi untuk merekam suara pengguna dan mengkonversinya menjadi teks
def record_and_transcribe(duration=10):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Silakan bicara...")
        audio = recognizer.listen(source, timeout=duration)
        print("Rekaman selesai.")

    try:
        transcribed_text = recognizer.recognize_google(audio, language="id-ID")
        print(f"Transcribed Text: {transcribed_text}")
        return transcribed_text
    except sr.UnknownValueError:
        print("Google Speech Recognition tidak dapat mengenali audio")
        return ""
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
        return ""

# Fungsi untuk mengotomatisasi interaksi dengan LLM
def automate_interaction(user_id, room_id, llm_response):

    user_response = record_and_transcribe()
    
    startingPrompt = ai_engine.initialize_prompt()
    result = ai_engine.generate_response(startingPrompt)
    
    if isinstance(result, tuple):
        result = {"response": result[0]}
    
    result.update({"user_id": user_id, "room_id": room_id})
    
    print(f"Result: {result}")
    
    try:
        response = requests.post('http://127.0.0.1:5000/virtual_assistant/test', json=result)
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending request: {e}")

# Inisialisasi sesi
user_id, room_id, llm_response = initialize_session()
text_to_speech(llm_response)

if user_id and room_id:
    automate_interaction(user_id, room_id, llm_response)
