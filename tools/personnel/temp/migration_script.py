# --- START OF FILE migration_script.py ---
import sqlite3

def run_migration():
    db_path = 'C:/Users/John Foliot/AppData/Roaming/MetaForge/metaforge.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("ALTER TABLE edges ADD COLUMN evidence_scope TEXT;")
        cursor.execute("ALTER TABLE edges ADD COLUMN evidence_detail TEXT;")
        
        conn.commit()
        print("Migration successful: evidence_scope and evidence_detail columns added to edges table.")
        
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_migration()
# --- END OF FILE migration_script.py ---