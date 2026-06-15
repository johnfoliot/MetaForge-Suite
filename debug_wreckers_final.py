# --- START OF FILE debug_wreckers_final.py ---
import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def surface_all_wreckers_data():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Get the Artist ID
    cursor.execute("SELECT * FROM library_artist WHERE artist_name LIKE '%The Wreckers%'")
    artists = cursor.fetchall()
    
    if not artists:
        print("No artist found named 'The Wreckers'.")
        conn.close()
        return

    for a in artists:
        aid = a['mf_artist_id']
        print(f"--- ARTIST FOUND: {a['artist_name']} (ID: {aid}) ---")
        
        # 2. Check library_master directly (using Column 9)
        cursor.execute("SELECT * FROM library_master WHERE mf_artist_id = ?", (aid,))
        masters = cursor.fetchall()
        print(f"\n--- ALBUMS IN library_master (Linked to Artist ID) ---")
        if not masters:
            print("NO ALBUMS FOUND in library_master for this Artist ID.")
        for m in masters:
            print(f"Album: {m['album_title']} | ID: {m['mf_id']}")
        
        # 3. Check Edges
        cursor.execute("SELECT * FROM edges WHERE target_id = ? OR source_id = ?", (aid, aid))
        edges = cursor.fetchall()
        print(f"\n--- EDGES TABLE ENTRIES ---")
        if not edges:
            print("No edges found.")
        for e in edges:
            print(f"Edge: Source({e['source_id']}) -> Target({e['target_id']}) | Relation: {e['relation_type']}")
            
    conn.close()

if __name__ == "__main__":
    surface_all_wreckers_data()
# --- END OF FILE debug_wreckers_final.py ---