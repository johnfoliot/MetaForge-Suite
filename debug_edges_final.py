# --- START OF FILE debug_edges_final.py ---
import sqlite3
from pathlib import Path

DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def debug_edges():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    # Your Artist ID
    aid = "f981c4c2a870844995bf3e53c3106af1e79cb4ad1939c2102b78b6657854888d"
    
    # Check both source_id and target_id columns
    cursor.execute("SELECT source_type, source_id, target_id, relation_type FROM edges WHERE source_id = ? OR target_id = ?", (aid, aid))
    rows = cursor.fetchall()
    
    if not rows:
        print(f"No edges found for ID: {aid}")
    else:
        print(f"{'Source Type':<15} | {'Source ID':<10} | {'Target ID':<10} | {'Relation':<10}")
        print("-" * 60)
        for r in rows:
            print(f"{r[0]:<15} | {r[1][:8]}... | {r[2][:8]}... | {r[3]:<10}")
    conn.close()

if __name__ == "__main__":
    debug_edges()
# --- END OF FILE debug_edges_final.py ---