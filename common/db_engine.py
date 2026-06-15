# --- START OF FILE db_engine.py ---
# ======================================================================
# MetaForge Shared Primitive: Database Engine
# Physical Location: \common\db_engine.py
# Build 1.0.2: Implemented Path Bootstrap for standalone unit testing.
# ======================================================================
import sqlite3
import sys
from pathlib import Path

# --- [ PATH BOOTSTRAP ] ---
# This logic allows the script to find the 'common' package when run directly.
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler

def get_connection():
    """
    Establishes a connection to the MetaForge Master Database.
    MUST be closed by the calling function to prevent locking.
    """
    db_path = config_handler.DB_PATH
    try:
        conn = sqlite3.connect(str(db_path))
        # Return rows as dictionaries for easier JS/JSON mapping
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"🔥 Database Connection Error: {e}")
        return None

def execute_query(query, params=(), commit=False):
    """
    Universal execution primitive for SELECT, INSERT, and UPDATE.
    """
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if commit:
            conn.commit()
            result = True
        else:
            result = [dict(row) for row in cursor.fetchall()]
            
        return result
    except sqlite3.Error as e:
        print(f"🔥 Query Execution Error: {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- [ DIAGNOSTIC SUITE ] ---
# This block only runs when the file is executed directly.

def run_diagnostics():
    print("\n--- MetaForge Primitive Diagnostic: Database Engine ---")
    
    # Test 1: Connectivity
    print("[1/2] Testing Connection to Master DB...", end=" ")
    conn = get_connection()
    if conn:
        print("PASS")
        conn.close()
    else:
        print("FAIL")
        return

    # Test 2: Query Execution
    print("[2/2] Testing Read/Write Integrity...", end=" ")
    # Create a temporary test table
    execute_query("CREATE TABLE IF NOT EXISTS _mf_diag (id INTEGER PRIMARY KEY, val TEXT)", commit=True)
    execute_query("INSERT INTO _mf_diag (val) VALUES (?)", ("Forensic_Check",), commit=True)
    
    res = execute_query("SELECT val FROM _mf_diag WHERE val = ?", ("Forensic_Check",))
    
    if res and res[0]['val'] == "Forensic_Check":
        print("PASS")
    else:
        print("FAIL")
    
    # Clean up
    execute_query("DROP TABLE _mf_diag", commit=True)
    print("--- Diagnostic Complete ---\n")

if __name__ == "__main__":
    run_diagnostics()

# --- END OF FILE db_engine.py ---