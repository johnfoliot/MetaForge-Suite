# --- START OF FILE verify_db.py ---
import sqlite3
import os

def verify_data(album_title):
    # Adjust the path to your database file if necessary
    db_path = "C:/Users/John Foliot/AppData/Roaming/MetaForge/metaforge.db" 
    
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"--- Verifying Records for Album: {album_title} ---\n")

    # 1. Get the mf_id for the album
    cursor.execute("SELECT mf_id FROM library_master WHERE album_title LIKE ?", (f"%{album_title}%",))
    res = cursor.fetchone()
    
    if not res:
        print(f"No album found matching: {album_title}")
        return

    mf_id = res[0]
    
    # 2. Query edges and join with library_artist to get names and roles
    query = """
        SELECT a.artist_name, e.role 
        FROM edges e
        JOIN library_artist a ON e.target_id = a.mf_artist_id
        WHERE e.source_id = ?
    """
    
    cursor.execute(query, (mf_id,))
    rows = cursor.fetchall()

    if not rows:
        print("No edges/personnel found for this album.")
    else:
        print(f"{'Artist Name':<30} | {'Role'}")
        print("-" * 50)
        for row in rows:
            print(f"{row[0]:<30} | {row[1]}")

    conn.close()

if __name__ == "__main__":
    verify_data("Animotion")
# --- END OF FILE verify_db.py ---