# --- START OF FILE debug_all_edges.py ---
import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def dump_all_edges():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Select all records from the edges table
    cursor.execute("SELECT * FROM edges")
    rows = cursor.fetchall()
    
    if not rows:
        print("The edges table is currently empty.")
    else:
        print(f"--- DUMPING {len(rows)} RECORDS FROM 'edges' TABLE ---")
        # Print header
        print(f"{'ID':<5} | {'Source ID (Artist/Album)':<20} | {'Target ID':<20} | {'Type':<10}")
        print("-" * 75)
        for r in rows:
            # Printing truncated IDs to make the output readable
            src = str(r['source_id'])[:15]
            tgt = str(r['target_id'])[:15]
            print(f"{r['id']:<5} | {src:<20} | {tgt:<20} | {r['relation_type']:<10}")
            
    conn.close()

if __name__ == "__main__":
    dump_all_edges()
# --- END OF FILE debug_all_edges.py ---