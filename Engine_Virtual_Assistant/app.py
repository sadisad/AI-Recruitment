import pyaudio
import wave
import json
from datetime import datetime
import sys
import os
from groq import Groq

# Tambahkan subdirektori ke sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules', 'db_module'))

from db_manager import save_absence

# Perekaman Suara
def record_audio(output_filename, duration=5):
    chunk = 1024  # Record in chunks of 1024 samples
    sample_format = pyaudio.paInt16  # 16 bits per sample
    channels = 1
    fs = 44100  # Record at 44100 samples per second
    p = pyaudio.PyAudio()  # Create an interface to PortAudio

    print('Recording')

    stream = p.open(format=sample_format,
                    channels=channels,
                    rate=fs,
                    frames_per_buffer=chunk,
                    input=True)

    frames = []  # Initialize array to store frames

    # Store data in chunks for the specified duration
    for _ in range(0, int(fs / chunk * duration)):
        data = stream.read(chunk)
        frames.append(data)

    # Stop and close the stream
    stream.stop_stream()
    stream.close()
    # Terminate the PortAudio interface
    p.terminate()

    print('Finished recording')

    # Save the recorded data as a WAV file
    wf = wave.open(output_filename, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(p.get_sample_size(sample_format))
    wf.setframerate(fs)
    wf.writeframes(b''.join(frames))
    wf.close()

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
            language="en",  # Optional
            temperature=0.0  # Optional
        )
        return transcription.text

# Otomatisasi Pengajuan Absen
def automate_absence_submission(file_path):
    text = transcribe_audio(file_path)
    if text is not None:
        print("Recognized Text:", text)

        # Contoh parsing dari teks yang dikenali
        text_lower = text.lower()
        if "absen" in text_lower or "izin" in text_lower or "cuti" in text_lower:
            name = "Alief"  # Parsing nama dari teks, bisa ditingkatkan dengan regex atau NLP
            date = datetime.now().strftime("%Y-%m-%d")  # Menggunakan tanggal saat ini
            reason = "Medical Leave"  # Parsing alasan dari teks, bisa ditingkatkan dengan regex atau NLP

            # Simpan ke MongoDB
            save_absence(name, date, reason)

            print("Pengajuan absen otomatis berhasil")
        else:
            print("Tidak ada permintaan absen yang terdeteksi")
    else:
        print("Tidak ada teks yang dikenali")

# Langkah-langkah Pengujian
output_filename = 'test_absence.wav'
record_audio(output_filename, duration=10)
automate_absence_submission(output_filename)