import sqlite3
import os

DB_FILE = r"E:\Project\Cockpit\app.db"  # adjust if needed

print("DB exists:", os.path.exists(DB_FILE))

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("\nTables found:")
for t in tables:
    print("-", t[0])

conn.close()
