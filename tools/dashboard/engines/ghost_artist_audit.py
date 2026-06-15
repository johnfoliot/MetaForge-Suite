# --- START OF FILE ghost_artist_audit.py ---
import sqlite3
from pathlib import Path

# Anchor to project root: \tools\dashboard\engines\ -> \..\..\
ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "AppData" / "Roaming" / "MetaForge" / "metaforge.db"

class Color:
    YELLOW = '\033[93m'
    WHITE  = '\033[97m'
    GRAY   = '\033[90m'
    RED    = '\033[91m'
    RESET  = '\033[0m'

def run_ghost_audit():
    if not DB_PATH.exists():
        print(f"{Color.RED}!! Error: Database not found at {DB_PATH}{Color.RESET}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # LOGIC:
    # 1. Start with the edges table (the graph).
    # 2. Filter for target_type = 'artist' (your personnel/artist index).
    # 3. Left Join with library_master (the definitive album/master index).
    # 4. Filter for rows where master side is NULL (the orphan/ghost).
    query = """
    SELECT DISTINCT e.target_id, e.role, e.id as edge_id
    FROM edges e
    LEFT JOIN library_master lm ON e.target_id = lm.mf_artist_id
    WHERE e.target_type = 'artist' 
      AND lm.mf_artist_id IS NULL
    ORDER BY e.target_id ASC
    """

    try:
        cursor.execute(query)
        orphans = cursor.fetchall()

        print(f"{Color.YELLOW}=== FORENSIC GHOST AUDIT: EDGES VS. MASTER ==={Color.RESET}")
        if not orphans:
            print(f"{Color.WHITE}No ghost personnel detected. Graph topology is sound.{Color.RESET}")
        else:
            for row in orphans:
                print(f"{Color.GRAY}EdgeID:{row['edge_id']:<5} | {Color.WHITE}TargetID: {row['target_id']:<20} | {Color.YELLOW}Role: {row['role']}{Color.RESET}")
            
            print(f"\n{Color.RED}TOTAL GHOSTS DETECTED: {len(orphans)}{Color.RESET}")
            print(f"{Color.GRAY}These entries exist in 'edges' but have no reciprocal link to 'library_master'.{Color.RESET}")

    except sqlite3.Error as e:
        print(f"{Color.RED}Database Error: {e}{Color.RESET}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_ghost_audit()
# --- END OF FILE ghost_artist_audit.py ---