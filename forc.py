import sqlite3

DB_FILE = "app.db"   # CHANGE this if your database file has a different name

def reset_user(username):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET device_id = NULL,
            is_logged_in = 0
        WHERE username = ?
    """, (username,))

    conn.commit()
    conn.close()

    print(f"User '{username}' has been reset.")

if __name__ == "__main__":
    reset_user("admin")
