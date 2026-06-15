import sqlite3
import os

# CONFIGURATION
DB_PATH = r"F:\MetaForge.db"

def run_queue_logic():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print(f"{'📋 METAFORGE: LIBRARY BIO WORK QUEUE':^80}")
    print("=" * 80)

    # query joins library_artist with tracks to count tracks per category/artist
    # checks if biography is NULL or empty
    query = """
        SELECT t.genre, a.artist_name, COUNT(t.file_path) as track_count
        FROM library_artist a
        JOIN tracks t ON a.mf_artist_id = t.mf_artist_id
        WHERE (a.biography IS NULL OR a.biography = '')
        GROUP BY t.genre, a.artist_name
        HAVING track_count >= 10
        ORDER BY t.genre ASC, a.artist_name ASC
    """

    cursor.execute(query)
    results = cursor.fetchall()

    current_cat = None
    priority_count = 0

    for cat, artist, count in results:
        if cat != current_cat:
            current_cat = cat
            print(f"\n[ CATEGORY: {current_cat} ]")
            print("-" * 40)
        
        print(f"  {artist:<40} | Tracks: {count}")
        priority_count += 1

    # Shadow List Query
    shadow_query = """
        SELECT a.artist_name, COUNT(t.file_path) as track_count
        FROM library_artist a
        JOIN tracks t ON a.mf_artist_id = t.mf_artist_id
        GROUP BY a.artist_name
        HAVING track_count < 10
        ORDER BY a.artist_name ASC
    """
    cursor.execute(shadow_query)
    shadow_results = cursor.fetchall()

    print("\n" + "=" * 80)
    print(f"Total Priority Bio Tasks: {priority_count}")
    print(f"Total Shadow Artists (Under 10 Tracks): {len(shadow_results)}")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    run_queue_logic()