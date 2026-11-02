import sqlite3
conn = sqlite3.connect('agentguard.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='authorization_reservations'")
result = cursor.fetchone()
print('authorization_reservations table exists:', result is not None)
if result:
    cursor.execute('PRAGMA table_info(authorization_reservations)')
    for col in cursor.fetchall():
        print(col)