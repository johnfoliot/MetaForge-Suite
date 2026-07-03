import sqlite3
import os

DB_PATH = r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"

def run_queue_logic():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print(f"{'📋 METAFORGE: FULL ARTIST APPEARANCE REPORT':^80}")
    print("=" * 80)

    query = """
        SELECT
            a.artist_name,
            a.mf_artist_id,
            COALESCE(track_counts.cnt, 0) AS track_count,
            COALESCE(edge_counts.cnt, 0) AS edge_count,
            COALESCE(track_counts.cnt, 0) + COALESCE(edge_counts.cnt, 0) AS total_appearances,
            CASE WHEN (a.biography IS NULL OR a.biography = '') THEN 'NO BIO' ELSE 'HAS BIO' END AS bio_status
        FROM library_artist a
        LEFT JOIN (
            SELECT mf_artist_id, COUNT(file_path) AS cnt
            FROM tracks
            GROUP BY mf_artist_id
        ) track_counts ON a.mf_artist_id = track_counts.mf_artist_id
        LEFT JOIN (
            SELECT target_id, COUNT(id) AS cnt
            FROM edges
            WHERE target_type = 'artist'
            GROUP BY target_id
        ) edge_counts ON a.mf_artist_id = edge_counts.target_id
        ORDER BY total_appearances DESC, a.artist_name ASC
    """

    cursor.execute(query)
    results = cursor.fetchall()

    no_bio_count = 0
    has_bio_count = 0

    print(f"\n  {'ARTIST':<40} | {'TRACKS':>7} | {'CREDITS':>7} | {'TOTAL':>6} | STATUS")
    print("-" * 80)

    for artist, mf_id, tracks, edges, total, status in results:
        marker = "🔴" if status == "NO BIO" else "🟢"
        print(f"  {artist:<40} | {tracks:>7} | {edges:>7} | {total:>6} | {marker} {status}")

        if status == "NO BIO":
            no_bio_count += 1
        else:
            has_bio_count += 1

    print("\n" + "=" * 80)
    print(f"Total Artists Listed: {len(results)}")
    print(f"Needs Bio: {no_bio_count}  |  Has Bio: {has_bio_count}")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    run_queue_logic()