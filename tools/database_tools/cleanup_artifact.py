import sqlite3
import sys
from pathlib import Path

# --- CONFIGURATION: HARD-CODED PATH ---
# Pointing directly to your local database
DB_PATH = "C:/Users/John Foliot/AppData/Roaming/MetaForge/metaforge.db"
# --------------------------------------

def run_cleanup():
    db_file = Path(DB_PATH)
    
    if not db_file.exists():
        print(f"CRITICAL ERROR: Database file not found at: {DB_PATH}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        print(f"Connecting to: {db_file}")
        target = "10cc"

        # Tables and their respective 'artist_name' columns based on your schema
        target_map = [
            ("library_artist", "artist_name"),
            ("library_master", "artist_name"),
        ]

        artifacts_found = False
        
        for table, col in target_map:
            cursor.execute(f"SELECT rowid, * FROM {table} WHERE {col} LIKE ?", (f"%{target}%",))
            results = cursor.fetchall()

            if results:
                artifacts_found = True
                print(f"\nFOUND {len(results)} ARTIFACT(S) in TABLE: {table}")
                for row in results:
                    print(f" -> {row}")
                
                confirm = input(f"Confirm PERMANENT DELETION from {table}? (y/n): ")
                if confirm.lower() == 'y':
                    cursor.execute(f"DELETE FROM {table} WHERE {col} LIKE ?", (f"%{target}%",))
                    conn.commit()
                    print(f"Surgical deletion from {table} complete.")
                else:
                    print(f"Skipped deletion for {table}.")

        if not artifacts_found:
            print(f"\nNo records found matching '{target}'. Database is already clean.")

    except sqlite3.Error as e:
        print(f"Database Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    run_cleanup()