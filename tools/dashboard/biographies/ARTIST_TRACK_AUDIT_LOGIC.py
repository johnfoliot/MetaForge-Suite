# // --- ARTIST TRACK AUDIT LOGIC ---
import sqlite3
import os

# CONFIGURATION
DB_PATH = r"F:\MetaForge.db"

os.system('') # Enable ANSI colors
class Color:
    YELLOW = '\033[93m' # Labels
    WHITE  = '\033[97m' # Output
    GRAY   = '\033[90m' # Messages
    RED    = '\033[91m' # Errors
    GREEN  = '\033[92m' # Success
    RESET  = '\033[0m'
    BOLD   = '\033[1m'

def run_artist_frequency_audit(threshold=10):
    """
    DEEP AUDIT: Groups by mf_artist_id to expose the individual performers.
    Sorted Alphabetically by Artist Name.
    """
    if not os.path.exists(DB_PATH):
        print(f"{Color.RED}!! Error: Database not found at {DB_PATH}{Color.RESET}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Query uses v12 Schema names: library_artist and tracks
    # Sorted Alphabetically (ASC) instead of by track count
    query = """
    SELECT 
        la.artist_name,
        COUNT(t.file_path) as track_count,
        la.biography,
        la.mf_artist_id
    FROM library_artist la
    LEFT JOIN tracks t ON la.mf_artist_id = t.mf_artist_id
    GROUP BY la.mf_artist_id
    ORDER BY la.artist_name ASC
    """

    print(f"\n{Color.YELLOW}{'='*80}{Color.RESET}")
    print(f"{Color.WHITE}{Color.BOLD}          📊 METAFORGE DEEP TRACK-LEVEL AUDIT{Color.RESET}")
    print(f"{Color.YELLOW}{'='*80}{Color.RESET}")
    print(f"{Color.YELLOW}{'ARTIST NAME':<40} | {'TRACKS':<8} | {'STATUS'}{Color.RESET}")
    print(f"{Color.GRAY}{'-'*80}{Color.RESET}")

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        
        lib_complete = 0 
        lib_pending = 0  
        shadow_count = 0

        for name, count, bio, mf_id in rows:
            # Determine Bio Status
            has_bio = True if (bio and len(bio.strip()) > 0 and bio.strip() not in ["[EMPTY]", "None"]) else False

            if count >= threshold:
                if not has_bio:
                    status = "NEEDS BIO"
                    status_color = Color.YELLOW
                    lib_pending += 1
                else:
                    status = "LIBRARY"
                    status_color = Color.GREEN
                    lib_complete += 1
            else:
                status = "SHADOW"
                status_color = Color.GRAY
                shadow_count += 1

            display_name = name if name else f"Unknown ({mf_id[:8]})"
            print(f"{Color.WHITE}{str(display_name)[:40]:<40}{Color.RESET} | "
                  f"{Color.WHITE}{str(count):<8}{Color.RESET} | "
                  f"{status_color}{status:<12}{Color.RESET}")

        print(f"{Color.GRAY}{'-'*80}{Color.RESET}")
        print(f"{Color.YELLOW}SUMMARY:{Color.RESET}")
        print(f"  {Color.WHITE}Unique Performers Found:               {len(rows)}{Color.RESET}")
        print(f"  {Color.GREEN}Library (Complete):                    {lib_complete}{Color.RESET}")
        print(f"  {Color.YELLOW}Library (Needs Bio):                   {lib_pending}{Color.RESET}")
        print(f"  {Color.GRAY}Shadow Artists:                        {shadow_count}{Color.RESET}")
        print(f"{Color.YELLOW}{'='*80}{Color.RESET}\n")

    except Exception as e:
        print(f"{Color.RED}!! Audit Failed: {e}{Color.RESET}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_artist_frequency_audit(threshold=10)