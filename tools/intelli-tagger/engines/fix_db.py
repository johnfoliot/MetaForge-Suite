# --- START OF FILE fix_db.py ---
import sqlite3
from pathlib import Path

# Adjust this path if your db is located elsewhere
DB_PATH = Path(r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db")

def fix_schema():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # List of columns and their host tables required by current build
    schema_updates = [
        ("tracks", "mb_work_id", "TEXT"),
        ("tracks", "orig_year_conf", "INTEGER"),
        ("tracks", "orig_year_source", "TEXT"),
        ("tracks", "leak_flag", "INTEGER"),
        ("library_master", "date_audit_status", "INTEGER")
    ]

    for table, col, col_type in schema_updates:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            print(f"Added column {col} to {table}.")
        except sqlite3.OperationalError:
            print(f"Column {col} already exists in {table}. Skipping.")

    conn.commit()
    conn.close()
    print("Database remediation complete.")

if __name__ == "__main__":
    fix_schema()
# --- END OF FILE fix_db.py ---