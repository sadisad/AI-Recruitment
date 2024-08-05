import pyaudio
import wave
import json
from datetime import datetime
import os
import time
import requests
import speech_recognition as sr
from gtts import gTTS
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment
from flask import session
from modules.ai_module.llm import LanguageModel
from modules.db_module.db_manager import DatabaseOperations
import pyttsx3
db_ops = DatabaseOperations()
# Memuat konfigurasi dari groq_config_llm.json
config_llm_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'groq_config_llm.json')
ai_engine = LanguageModel()
# Memuat konfigurasi dari elevenlabs_config.json
config_elevenlabs_path = os.path.join(os.path.dirname(__file__), 'modules', 'ai_module', 'elevenlabs_config.json')
with open(config_elevenlabs_path, 'r') as f:
    config_elevenlabs = json.load(f)
# Inisialisasi Eleven Labs
elevenlabs_client = ElevenLabs(api_key=config_elevenlabs['api_key'])
# Fungsi untuk menginisialisasi sesi dan mendapatkan user_id dan room_id
def initialize_session():
    headers = {'Content-Type': 'application/json'}
    response = requests.post('http://127.0.0.1:5000/virtual_assistant/initialize', headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(data['llm_response'])
        return data
    else:
        print("Failed to initialize session")
        return None
def process_input(user_input, session_data):
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post('http://127.0.0.1:5000/virtual_assistant/process', json={
            'input': user_input,
            'session_data': session_data
        }, headers=headers)
        try:
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print("Failed to process input")
                return None
        except Exception as e:
            print(f'error : {e}')
    except Exception as e:
        print(f'error : {e}')
# Fungsi untuk mengubah teks menjadi suara
def text_to_speech(text, language='id', service='gtts'):
    if service == 'gtts':
        tts = gTTS(text=text, lang=language)
        mp3_filename = "speech.mp3"
        wav_filename = "speech.wav"
        tts.save(mp3_filename)
        # Konversi file mp3 ke wav menggunakan pydub
        AudioSegment.from_mp3(mp3_filename).export(wav_filename, format="wav")
    elif service == 'elevenlabs':
        audio_data = elevenlabs_client.text_to_speech.convert(
            voice_id="cgSgspJ2msm6clMCkdW9",  # Pastikan voice_id mendukung bahasa yang Anda inginkan
            optimize_streaming_latency="0",
            output_format="mp3_22050_32",
            text=text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=1,
                similarity_boost=0.7,
                style=0.2,
                language=language  # Menentukan bahasa yang diinginkan
            ),
        )
        mp3_filename = "speech.mp3"
        wav_filename = "speech.wav"
        audio_bytes = b"".join(audio_data)  # Mengubah generator menjadi objek byte
        with open(mp3_filename, "wb") as f:
            f.write(audio_bytes)
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
def automate_interaction(user_id, room_id, llm_response, session):
    keep_talking = True
    session_data = session
    ai_engine.initialize_api_type('Virtual Assistant', session_data)
    while keep_talking:
        user_response = record_and_transcribe()
        db_ops.upsert_conversation_transcript(room_id, user_response, 'User')
        if str(user_response).strip() == "":
            keep_talking = False
            print("Penghentian interaksi karena tidak ada jawaban.")
            break
        session_data['history'].append({"role": "user", "content": user_response})
        try:
            # Send transcribed text to AI engine to get a response
            response_data = process_input(user_response, session_data)
            if response_data:
                ai_response = str(response_data['message'])
                session_data['history'].append({"role": "system", "content": ai_response})
                db_ops.upsert_conversation_transcript(room_id, ai_response, 'AI')
                # Print AI response
                print(f"AI Response: {ai_response}")
                # Convert AI response to speech and play
                text_to_speech(ai_response, language='id', service='elevenlabs')  # Menggunakan ElevenLabs
            else:
                print("Error processing input")
                break
        except Exception as e:
            print(f'error : {e}')
            break
# Initialize session
data = initialize_session()
# Menggunakan ElevenLabs untuk text_to_speech
# switch 'elevenlabs' / 'gtts'
text_to_speech(data['llm_response'], language='id', service='gtts')
if data['user_id'] and data['room_id']:
    automate_interaction(data['user_id'], data['room_id'], data['llm_response'], data['session_data'])