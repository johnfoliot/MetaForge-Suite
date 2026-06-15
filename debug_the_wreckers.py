# --- START OF FILE debug_the_wreckers.py ---
import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def find_wreckers():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # 1. Find the artist ID by name
    cursor.execute("SELECT mf_artist_id FROM library_artist WHERE artist_name = 'The Wreckers'")
    row = cursor.fetchone()
    
    if not row:
        print("Artist 'The Wreckers' not found in library_artist table.")
        return
        
    aid = row[0]
    print(f"Artist found. ID: {aid}")
    
    # 2. Check if ANY albums exist for this ID in the master table via edges
    cursor.execute("SELECT * FROM edges WHERE target_id = ?", (aid,))
    edges = cursor.fetchall()
    print(f"Edges found: {len(edges)}")
    
    conn.close()

if __name__ == "__main__":
    find_wreckers()
# --- END OF FILE debug_the_wreckers.py ---