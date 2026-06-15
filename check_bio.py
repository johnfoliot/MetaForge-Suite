# --- START OF FILE check_bio.py ---
import sqlite3
from pathlib import Path

# Path to your database
DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def check_artist_bio(artist_name):
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    # Using Row factory allows us to access columns by name
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"Searching for artist: {artist_name}...")
    
    cursor.execute("SELECT artist_name, bio_text FROM library_artist WHERE artist_name LIKE ?", (f"%{artist_name}%",))
    rows = cursor.fetchall()

    if not rows:
        print("No artist found matching that name.")
    else:
        for row in rows:
            print(f"\n--- Artist Found: {row['artist_name']} ---")
            bio = row['bio_text']
            if bio:
                print(f"Biography Found ({len(bio)} characters):")
                print(bio[:300] + "..." if len(bio) > 300 else bio)
            else:
                print("Biography column is empty (NULL or empty string).")
    
    conn.close()

if __name__ == "__main__":
    check_artist_bio("The Wreckers")
# --- END OF FILE check_bio.py ---