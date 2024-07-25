from gtts import gTTS
from playsound import playsound
import os

def speak(text, language='id'):
    tts = gTTS(text=text, lang=language)
    filename = "speech.mp3"
    tts.save(filename)
    playsound(filename)
    os.remove(filename)
