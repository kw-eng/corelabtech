import sqlite3

# funkcja tworząca połączenie z bazą danych
def db():
    con = sqlite3.connect("data/database.db")
    
    return con