import pyaudio
import wave
import json
from datetime import datetime
import sys
import os
from groq import Groq
import requests
from flask import Flask, session
from flask_session import Session

from flask import jsonify
# Tambahkan subdirektori ke sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules', 'db_module'))

# Memuat file konfigurasi LLM
config_llm_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'groq_config_llm.json')

from modules.ai_module.llm import LanguageModel
ai_engine = LanguageModel()

# Perekaman Suara
# def record_audio(output_filename, duration=5):
#     chunk = 1024  # Record in chunks of 1024 samples
#     sample_format = pyaudio.paInt16  # 16 bits per sample
#     channels = 1
#     fs = 44100  # Record at 44100 samples per second
#     p = pyaudio.PyAudio()  # Create an interface to PortAudio

#     print('Recording')

#     stream = p.open(format=sample_format,
#                     channels=channels,
#                     rate=fs,
#                     frames_per_buffer=chunk,
#                     input=True)

#     frames = []  # Initialize array to store frames

#     # Store data in chunks for the specified duration
#     for _ in range(0, int(fs / chunk * duration)):
#         data = stream.read(chunk)
#         frames.append(data)

#     # Stop and close the stream
#     stream.stop_stream()
#     stream.close()
#     # Terminate the PortAudio interface
#     p.terminate()

#     print('Finished recording')

#     # Save the recorded data as a WAV file
#     wf = wave.open(output_filename, 'wb')
#     wf.setnchannels(channels)
#     wf.setsampwidth(p.get_sample_size(sample_format))
#     wf.setframerate(fs)
#     wf.writeframes(b''.join(frames))
#     wf.close()

# Konversi Suara Menjadi Teks
config_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'groq_config_whisper.json')
with open(config_path) as config_file:
    config = json.load(config_file)

api_key = config["api_key"]
model = config["model"]

client = Groq(api_key=api_key)

def transcribe_audio(file_path):
    with open(file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(file_path, file.read()),
            model=model,
            prompt="",  # Optional
            response_format="json",  # Optional
            language="id",  # Optional
            temperature=0.0  # Optional
        )
        return transcription.text

def automate_demo(file_path, user_id, room_id):
    transcribed_text = transcribe_audio(file_path)
    print(f"Transcribed Text: {transcribed_text}")
    
    startingPrompt = ai_engine.initialize_prompt(transcribed_text)
    result = ai_engine.generate_response(startingPrompt)
    
    result.update({"user_id": user_id, "room_id": room_id})
    
    print(f"Result: {result}")
    
    try:
        response = requests.post('http://127.0.0.1:5000/virtual%20assistant/test', json=result)
        response.raise_for_status()
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending request: {e}")

# Langkah-langkah Pengujian
output_filename = 'test_absence.wav'
# record_audio(output_filename, duration=10)

# Inisialisasi sesi dan dapatkan user_id dan room_id
response = requests.post('http://127.0.0.1:5000/Virtual Assistant/initialize')
if response.status_code == 200:
    data = response.json()
    user_id = data['user_id']
    room_id = data['room_id']
    automate_demo(output_filename, user_id, room_id)
else:
    print("Failed to initialize session")