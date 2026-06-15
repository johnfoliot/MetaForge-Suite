# --- START OF FILE remediate_db.py ---
# ======================================================================
# MetaForge Database Remediation Utility
# Role: Syncs production schema with current Intelli-Tagger requirements.
# Build 1.0.0
# ======================================================================
import sqlite3
import os

DB_PATH = r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"

def run_remediation():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("Starting schema remediation...")

        # Remediating tracks table
        try:
            cursor.execute("ALTER TABLE tracks ADD COLUMN mb_work_id TEXT")
            print("Successfully added 'mb_work_id' to [tracks].")
        except sqlite3.OperationalError:
            print("'mb_work_id' column already exists in [tracks]. Skipping.")

        # Remediating library_master table
        try:
            cursor.execute("ALTER TABLE library_master ADD COLUMN date_audit_status TEXT")
            print("Successfully added 'date_audit_status' to [library_master].")
        except sqlite3.OperationalError:
            print("'date_audit_status' column already exists in [library_master]. Skipping.")

        conn.commit()
        conn.close()
        print("Remediation complete. Database is now in sync.")

    except Exception as e:
        print(f"Critical Failure: {str(e)}")

if __name__ == "__main__":
    run_remediation()
# --- END OF FILE remediate_db.py ---