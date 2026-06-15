# ======================================================================
# MetaForge Studio: Artist Enumeration Utility
# Purpose: List all artists and their roles (Primary/Backup) from DB
# ======================================================================
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path to access common.config_handler
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from common import config_handler

def fetch_artist_roles():
    """
    Queries the database for all artists and joins them with the edges table
    to determine their primary/backup status.
    """
    db_path = config_handler.DB_PATH
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query: Select artists and their role from the edges table.
    # We use a LEFT JOIN to ensure artists without edge definitions are still listed.
    query = """
    SELECT
        a.artist_name,
        a.mf_artist_id,
        COALESCE(e.role, 'None') as role
    FROM library_artist a
    LEFT JOIN edges e ON a.mf_artist_id = e.target_id
    ORDER BY a.artist_name ASC
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        results = []
    finally:
        conn.close()
        
    return results

def main():
    print("--- MetaForge Artist Registry ---")
    artists = fetch_artist_roles()
    
    if not artists:
        print("No artists found in the library.")
        return

    # Print formatted output
    header = f"{'Artist Name':<30} | {'MF Artist ID':<15} | {'Role'}"
    print(header)
    print("-" * len(header))
    
    for name, artist_id, role in artists:
        # Truncate long names for alignment
        display_name = (name[:27] + '..') if len(name) > 30 else name
        print(f"{display_name:<30} | {artist_id:<15} | {role}")

if __name__ == "__main__":
    main()