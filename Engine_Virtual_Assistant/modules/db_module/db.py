import sqlite3

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('interactions.db')
        self.create_table()
    
    def create_table(self):
        query = '''CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY,
                    user_input TEXT,
                    response TEXT
                   )'''
        self.conn.execute(query)
        self.conn.commit()
    
    def save_interaction(self, user_input, response):
        query = '''INSERT INTO interactions (user_input, response) VALUES (?, ?)'''
        self.conn.execute(query, (user_input, response))
        self.conn.commit()
