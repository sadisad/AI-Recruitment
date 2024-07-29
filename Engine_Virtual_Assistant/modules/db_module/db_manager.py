import pymongo
import json
import os

# Baca konfigurasi database dari file schema_info.json
config_path = os.path.join(os.path.dirname(__file__), 'schema_info.json')
with open(config_path) as config_file:
    config = json.load(config_file)

# Pastikan semua kunci ada dalam file konfigurasi
if "uri" not in config or "database" not in config or "collection" not in config:
    raise KeyError("File konfigurasi harus memiliki kunci 'uri', 'database', dan 'collection'")

# Koneksi ke MongoDB
client = pymongo.MongoClient(config["uri"])
db = client[config["database"]]
collection = db[config["collection"]]

def save_absence(name, date, reason):
    absence_record = {
        "name": name,
        "date": date,
        "reason": reason
    }
    result = collection.insert_one(absence_record)
    return result.inserted_id
