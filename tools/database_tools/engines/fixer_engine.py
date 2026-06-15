# --- START OF FILE fixer_engine.py ---
import sqlite3
from flask import jsonify, request
from common import config_handler

def handle(action):
    data = request.get_json() or {}
    target_type = data.get("type")
    target_id = data.get("id")
    
    # --- ACTION: DIAGNOSE ---
    if action == "diagnose":
        term = data.get("term", "").strip()
        cat = data.get("category", "all")
        if not term: return jsonify({"status": "error", "message": "Search term required."})
        
        try:
            conn = sqlite3.connect(config_handler.DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            search_term = f"%{term}%"
            results = []

            # Exhaustive Scan for Collisions
            if cat in ["all", "track"]:
                cursor.execute("SELECT rowid, title FROM tracks WHERE title LIKE ?", (search_term,))
                results.extend([{"id": r[0], "type": "track", "display": r[1]} for r in cursor.fetchall()])
            
            if cat in ["all", "album"]:
                cursor.execute("SELECT rowid, album_title FROM library_master WHERE album_title LIKE ?", (search_term,))
                results.extend([{"id": r[0], "type": "album", "display": r[1]} for r in cursor.fetchall()])
            
            if cat in ["all", "artist"]:
                cursor.execute("SELECT rowid, artist_name FROM library_artist WHERE artist_name LIKE ?", (search_term,))
                results.extend([{"id": r[0], "type": "artist", "display": r[1]} for r in cursor.fetchall()])
            
            if cat in ["all", "personnel"]:
                cursor.execute("SELECT rowid, role FROM edges WHERE role LIKE ?", (search_term,))
                results.extend([{"id": r[0], "type": "personnel", "display": f"{r[1]} (role)"} for r in cursor.fetchall()])

            conn.close()
            return jsonify({"status": "success", "data": results})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --- ACTION: PURGE ---
    elif action == "purge":
        try:
            conn = sqlite3.connect(config_handler.DB_PATH, timeout=10)
            cursor = conn.cursor()
            
            # 1. DEEP PURGE: ARTIST
            if target_type == "artist":
                cursor.execute("SELECT mf_artist_id FROM library_artist WHERE rowid = ?", (target_id,))
                row = cursor.fetchone()
                if row:
                    mf_artist_id = row[0]
                    # Cascade: Clean Edges, Master, Tracks, then Artist
                    cursor.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (mf_artist_id, mf_artist_id))
                    cursor.execute("DELETE FROM library_master WHERE mf_artist_id = ?", (mf_artist_id,))
                    cursor.execute("DELETE FROM tracks WHERE mf_artist_id = ?", (mf_artist_id,))
                    cursor.execute("DELETE FROM library_artist WHERE rowid = ?", (target_id,))
            
            # 2. DEEP PURGE: ALBUM
            elif target_type == "album":
                cursor.execute("SELECT mf_id FROM library_master WHERE rowid = ?", (target_id,))
                row = cursor.fetchone()
                if row:
                    mf_id = row[0]
                    # Cascade: Clean Edges, Tracks, then Master (Album)
                    cursor.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (mf_id, mf_id))
                    cursor.execute("DELETE FROM tracks WHERE mf_id = ?", (mf_id,))
                    cursor.execute("DELETE FROM library_master WHERE rowid = ?", (target_id,))
            
            # 3. PURGE: PERSONNEL (Edge specific)
            elif target_type == "personnel":
                cursor.execute("DELETE FROM edges WHERE rowid = ?", (target_id,))
                
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": f"Purge complete: {target_type} and all descendants removed."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
            
    return jsonify({"status": "error", "message": "Invalid action"}), 400
# --- END OF FILE fixer_engine.py ---