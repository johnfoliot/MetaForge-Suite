# --- START OF FILE debug_albums.py ---
import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def debug():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    # Replace the ID below with the one from your logs: f981c4c2...
    target_id = "f981c4c2a870844995bf3e53c3106af1e79cb4ad1939c2102b78b6657854888d"
    
    print(f"Checking edges for artist: {target_id}")
    cursor.execute("SELECT * FROM edges WHERE target_id = ?", (target_id,))
    rows = cursor.fetchall()
    
    if not rows:
        print("CRITICAL: No edges found for this artist ID. Check if the ID in the edges table matches.")
    else:
        print(f"Found {len(rows)} edge records. Sample: {rows[0]}")
    conn.close()

if __name__ == "__main__":
    debug()
# --- END OF FILE debug_albums.py ---