import sqlite3
import os
import hashlib
from pathlib import Path

# // --- VERSION TRACKER: v.2026.02 ---
# // --- TARGET: "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db" ---

# // --- CONFIGURATION ---
DB_PATH = r"C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"

os.system('') # Enable ANSI colors for Windows Terminal
class Color:
    YELLOW = '\033[93m'
    GREEN  = '\033[92m'
    RED    = '\033[91m'
    WHITE  = '\033[97m'
    RESET  = '\033[0m'
    BOLD   = '\033[1m'
    GRAY   = '\033[90m'

def format_val(val):
    """Returns formatted string or [EMPTY] indicator."""
    if val is None or str(val).strip() in ["", "None", "[EMPTY]"]:
        return f"{Color.GRAY}[EMPTY]{Color.RESET}"
    return str(val)

def get_energy_bar(value):
    try:
        val = int(float(value))
        bar = "█" * val + "░" * (10 - val)
        return f"[{bar}] ({val}/10)"
    except:
        return f"{Color.GRAY}[N/A]{Color.RESET}"

def get_album_snapshot(input_path):
    """
    3-table relational inspection using MetaForge standardized anchors.
    Ensures UI consistency across the new 2026 schema.
    """
    # Normalize path for SQLite search
    raw_path = input_path.strip().strip('"').replace('\\', '/')
    
    if not os.path.exists(DB_PATH):
        print(f"  {Color.RED}!! Database not found at: {DB_PATH}{Color.RESET}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. Anchor: Get the track record
        search_query = f"%{raw_path}%"
        cursor.execute("SELECT * FROM tracks WHERE file_path LIKE ? LIMIT 1", (search_query,))
        track_sample = cursor.fetchone()

        if not track_sample:
            print(f"  {Color.RED}!! No Record found in [tracks] for path: {raw_path}{Color.RESET}")
            return

        mf_id = track_sample['mf_id']
        mf_artist_id = track_sample['mf_artist_id']

        # 2. Fetch Relational Rows via Anchors
        cursor.execute("SELECT * FROM library_master WHERE mf_id = ?", (mf_id,))
        master_row = cursor.fetchone()

        cursor.execute("SELECT * FROM library_artist WHERE mf_artist_id = ?", (mf_artist_id,))
        artist_row = cursor.fetchone()

        # UI OUTPUT HEADER
        album_name = master_row['album_title'] if master_row else "Unknown Album"
        print(f"\n{Color.YELLOW}{'='*75}{Color.RESET}")
        print(f"  {Color.YELLOW}{Color.BOLD}METAFORGE RELATIONAL AUDIT:{Color.RESET} {Color.WHITE}{album_name}{Color.RESET}")
        print(f"  {Color.GRAY}mf_id: {mf_id}{Color.RESET}")
        print(f"  {Color.GRAY}mf_artist_id: {mf_artist_id}{Color.RESET}")
        print(f"{Color.YELLOW}{'='*75}{Color.RESET}")
        
        # --- DISPLAY: library_artist ---
        print(f"\n  {Color.YELLOW}{Color.BOLD}TABLE: Artist Master [library_artist]{Color.RESET}")
        print(f"  {Color.YELLOW}{'-'*71}{Color.RESET}")
        if artist_row:
            for col in artist_row.keys():
                val = artist_row[col]
                # Special handling for the new Biography lifecycle
                if col == 'biography':
                    status = f"{Color.GREEN}[DATA PRESENT]{Color.RESET}" if val and len(val) > 10 else f"{Color.RED}[NEEDS BIO]{Color.RESET}"
                    print(f"    {Color.WHITE}{col:<20}{Color.RESET} : {status}")
                else:
                    print(f"    {Color.WHITE}{col:<20}{Color.RESET} : {format_val(val)}")
        else:
            print(f"    {Color.RED}!! No artist profile found for this anchor.{Color.RESET}")

        # --- DISPLAY: library_master ---
        print(f"\n  {Color.YELLOW}{Color.BOLD}TABLE: Album Master [library_master]{Color.RESET}")
        print(f"  {Color.YELLOW}{'-'*71}{Color.RESET}")
        if master_row:
            for col in master_row.keys():
                print(f"    {Color.WHITE}{col:<20}{Color.RESET} : {format_val(master_row[col])}")
        else:
            print(f"    {Color.RED}!! No record found in library_master{Color.RESET}")

        # --- DISPLAY: tracks ---
        print(f"\n  {Color.YELLOW}{Color.BOLD}TABLE: Atomic Track [tracks (Sample Record)]{Color.RESET}")
        print(f"  {Color.YELLOW}{'-'*71}{Color.RESET}")
        if track_sample:
            cursor.execute("SELECT COUNT(*) FROM tracks WHERE mf_id = ?", (mf_id,))
            total_tracks = cursor.fetchone()[0]
            print(f"    {Color.WHITE}{'ALBUM TRACK COUNT':<20}{Color.RESET} : {Color.BOLD}{total_tracks}{Color.RESET}")
            
            for col in track_sample.keys():
                val = track_sample[col]
                if col == 'intensity':
                    print(f"    {Color.WHITE}{col:<20}{Color.RESET} : {get_energy_bar(val)}")
                else:
                    print(f"    {Color.WHITE}{col:<20}{Color.RESET} : {format_val(val)}")

        # --- DISPLAY: edges (Personnel) ---
        # Personnel data lives entirely in edges -- library_master's old
        # legacy flat "personnel" text column (write-only, never read by
        # any real UI) was removed 2026-07-06.
        print(f"\n  {Color.YELLOW}{Color.BOLD}TABLE: Personnel [edges]{Color.RESET}")
        print(f"  {Color.YELLOW}{'-'*71}{Color.RESET}")
        cursor.execute(
            "SELECT e.role, e.relation_type, a.artist_name as name, e.confidence, e.provenance "
            "FROM edges e JOIN library_artist a ON e.target_id = a.mf_artist_id "
            "WHERE e.source_id = ? AND e.source_type = 'album'",
            (mf_id,)
        )
        personnel_rows = cursor.fetchall()
        if personnel_rows:
            for row in personnel_rows:
                name = row['name'] or "Unknown Artist"
                role = (row['role'] or "Unknown Role").strip()
                conf = row['confidence']
                conf_str = f"{conf:.1f}" if conf is not None else "N/A"
                print(f"    {Color.WHITE}{name:<25}{Color.RESET} : {role:<25} ({row['relation_type']}, conf {conf_str}, {format_val(row['provenance'])})")
        else:
            print(f"    {Color.GRAY}No personnel/edges records found for this album.{Color.RESET}")

        print(f"\n{Color.YELLOW}{'='*75}{Color.RESET}")

    except Exception as e:
        print(f"  {Color.RED}Audit Error: {e}{Color.RESET}")
    finally:
        conn.close()

if __name__ == "__main__":
    print(f"\n{Color.YELLOW}{'='*75}{Color.RESET}")
    print(f"{Color.WHITE}{Color.BOLD}          🔬  MetaForge Relational Inspector 🔬{Color.RESET}")
    print(f"{Color.YELLOW}{'='*75}{Color.RESET}")

    while True:
        path_input = input(f"\n  {Color.WHITE}Paste Album Path to Inspect (or 'Q' to quit):\n  📂 {Color.RESET}").strip()
        if path_input.upper() == 'Q':
            break
        if path_input:
            get_album_snapshot(path_input)