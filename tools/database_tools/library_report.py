import sqlite3
import os

def generate_library_report(db_path):
    if not os.path.exists(db_path):
        print(f"Error: The database file was not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query to get unique genre-artist-album relationships
        query = """
        SELECT DISTINCT 
            T.genre, 
            LA.artist_name, 
            LM.album_title
        FROM tracks T
        JOIN library_artist LA ON T.mf_artist_id = LA.mf_artist_id
        JOIN library_master LM ON LA.mf_artist_id = LM.mf_artist_id
        ORDER BY T.genre, LA.artist_name, LM.album_title
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Organize data into a nested dictionary
        library_map = {}
        for genre, artist, album in rows:
            if genre not in library_map:
                library_map[genre] = {}
            if artist not in library_map[genre]:
                library_map[genre][artist] = set()
            library_map[genre][artist].add(album)
            
        # Print the formatted report
        for genre in sorted(library_map.keys()):
            print(f"{genre}")
            for artist in sorted(library_map[genre].keys()):
                print(f"     {artist}")
                for album in sorted(library_map[genre][artist]):
                    print(f"          {album}")
            print()

        conn.close()

    except sqlite3.Error as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    db_file = r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
    generate_library_report(db_file)