import sqlite3
conn = sqlite3.connect('EauVive_prix.db')
tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print("Tables:", tables)
if 'MAGASINS' in tables:
    cols = [c[1] for c in conn.execute("PRAGMA table_info(MAGASINS)").fetchall()]
    print("MAGASINS cols:", cols)
conn.close()
