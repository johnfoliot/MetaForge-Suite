# --- START OF FILE check_db.py ---
import sqlite3
import os

# 1. UPDATE THIS PATH to point to your actual database file
DB_PATH = r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"

def inspect_album_data():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # We join 'tracks' with 'library_master' to filter by album_title
        query = """
        SELECT t.* FROM tracks t
        JOIN library_master m ON t.mf_id = m.mf_id
        WHERE m.album_title = 'Stand Still, Look Pretty' AND m.artist_name = 'The Wreckers'
        ORDER BY t.file_path ASC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        colnames = [description[0] for description in cursor.description]
        print(f"Found {len(rows)} tracks for 'Stand Still, Look Pretty' by 'The Wreckers':\n")
        
        # Print column names and data
        print(" | ".join(colnames))
        print("-" * 100)
        
        for row in rows:
            print(" | ".join(map(str, row)))

        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    inspect_album_data()
    
# --- END OF FILE check_db.py ---