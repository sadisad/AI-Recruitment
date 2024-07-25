import speech_recognition as sr

def get_microphone_index(mic_name):
    for index, name in enumerate(sr.Microphone.list_microphone_names()):
        if mic_name in name:
            return index
    return None

def listen(mic_index=None, timeout=5, language='id-ID'):
    recognizer = sr.Recognizer()
    with sr.Microphone(device_index=mic_index) as source:
        print("Adjusting for ambient noise, please wait...")
        recognizer.adjust_for_ambient_noise(source)
        print("Mulai berbicara sekarang...")
        try:
            audio = recognizer.listen(source, timeout=timeout)
            text = recognizer.recognize_google(audio, language=language)
            # Check for non-acceptable answers
            if text.lower() in ["tidak tahu", "ga tahu"]:
                print("Jawaban tidak dapat diterima.")
                return None
        except sr.WaitTimeoutError:
            print(f"Tidak ada suara yang terdeteksi dalam {timeout} detik.")
            return None
        except sr.UnknownValueError:
            print("Maaf, saya tidak mengerti apa yang Anda katakan.")
            return None
        except sr.RequestError as e:
            print(f"Tidak bisa mendapatkan hasil dari server Google Speech Recognition; {e}")
            return None
    return text
