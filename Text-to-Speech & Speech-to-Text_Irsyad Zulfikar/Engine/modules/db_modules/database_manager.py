import sqlite3

def save_to_db(data, db_filename='form_data.db'):
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 nama_panjang TEXT,
                 nomor_telepon TEXT,
                 tempat_tanggal_lahir TEXT,
                 alamat TEXT,
                 hobi TEXT)''')
    c.execute("INSERT INTO users (nama_panjang, nomor_telepon, tempat_tanggal_lahir, alamat, hobi) VALUES (?, ?, ?, ?, ?)", 
              (data.get('Nama Panjang'),
               data.get('Nomor Telepon'),
               data.get('Tempat Tanggal Lahir'),
               data.get('Alamat'),
               data.get('Hobi')))
    conn.commit()
    conn.close()
