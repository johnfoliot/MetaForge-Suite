# --- START OF FILE master_db_sync.py ---
import sqlite3
from pathlib import Path

# Database path as defined in your configuration
DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def sync_schema():
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Defined Schema requirements for latest build
    # Format: (Table, Column, Type)
    required_cols = [
        ("tracks", "length", "INTEGER"),
        ("tracks", "orig_year_source", "TEXT"),
        ("tracks", "leak_flag", "INTEGER"),
        ("tracks", "mb_work_id", "TEXT"),
        ("tracks", "orig_year_conf", "INTEGER"),
        ("library_master", "date_audit_status", "INTEGER")
    ]

    print("Initiating full schema synchronization...")
    
    for table, col, col_type in required_cols:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            print(f" [+] Added missing column: {col} to {table}")
        except sqlite3.OperationalError:
            print(f" [=] Column {col} already exists in {table}.")

    conn.commit()
    conn.close()
    print("Schema sync complete. Database is now compatible with the current build.")

if __name__ == "__main__":
    sync_schema()
# --- END OF FILE master_db_sync.py ---