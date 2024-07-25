from modules.file_processor_modules.text_to_speech import speak
from modules.file_processor_modules.speech_to_text import listen, get_microphone_index
from modules.db_modules.database_manager import save_to_db

mic_name = "EDIFIER NeoBuds Pro 2"
mic_index = get_microphone_index(mic_name)

data = {}

speak("Halo. Perkenalkan saya AI Linov Roket Prestasi. Terima kasih telah mendaftar menjadi member linov roket prestasi. Bolehkah aku meminta nama panjang mu?")
data['Nama Panjang'] = listen(mic_index)

speak("Baik, selanjutnya, berikan nomor telepon mu.")
data['Nomor Telepon'] = listen(mic_index)

speak("Terima kasih. Sekarang, tolong beritahu saya tempat dan tanggal lahir Anda.")
data['Tempat Tanggal Lahir'] = listen(mic_index)

speak("Sekarang, mohon berikan alamat Anda.")
data['Alamat'] = listen(mic_index)

speak("Terakhir, apa hobi Anda?")
data['Hobi'] = listen(mic_index)

if all(value is not None for value in data.values()):
    save_to_db(data)
    speak("Data Anda telah berhasil disimpan. Terima kasih.")
else:
    speak("Pendaftaran gagal karena ada data yang tidak lengkap atau jawaban 'tidak tahu'.")
