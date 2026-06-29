# --- START OF FILE biography.py ---
# ======================================================================
# MetaForge Tool: Biography Builder Logic
# File Location: \tools\biography\biography.py
# Build 1.0.7: Enforced Image Resizing and Local File Handling
# ======================================================================
import hashlib
import requests
import shutil
from flask import request, jsonify
from google import genai
from common import config_handler, db_engine, image_processor

def get_md5_hash(artist_name):
    return hashlib.md5(artist_name.lower().encode('utf-8')).hexdigest()

def get_hashed_path(artist_name):
    hash_val = get_md5_hash(artist_name)
    photos_dir = config_handler.PROJECT_ROOT / "photos"
    if not photos_dir.exists():
        photos_dir.mkdir(parents=True)
    return photos_dir / f"{hash_val}.jpg"

def process_and_save_image(source_data_or_path, target_path, is_local=False):
    """Handles binary data or local file copy with 500x500 archival resizing."""
    try:
        if is_local:
            shutil.copy2(source_data_or_path, target_path)
            raw_data = open(target_path, 'rb').read()
        else:
            raw_data = source_data_or_path
        return image_processor.apply_archival_fit(raw_data, target_path, size=(500, 500))
    except Exception as e:
        print(f"[BioBuilder] Processing Error: {e}")
        return False

def fetch_artist_portrait(artist_name, target_path):
    token = config_handler.DISCOGS_TOKEN
    headers = {"User-Agent": "MetaForge/1.0", "Authorization": f"Discogs token={token}"}
    try:
        search_url = f"https://api.discogs.com/database/search?q={artist_name}&type=artist"
        res = requests.get(search_url, headers=headers, timeout=10).json()
        if not res.get('results'): return False
        artist_url = res['results'][0]['resource_url']
        artist_data = requests.get(artist_url, headers=headers, timeout=10).json()
        images = artist_data.get('images', [])
        img_url = next((i['uri'] for i in images if i.get('type') == 'primary'), None)
        if img_url:
            img_req = requests.get(img_url, headers=headers, timeout=10)
            return process_and_save_image(img_req.content, target_path)
    except Exception as e:
        print(f"[BioBuilder] Image Fetch Error: {e}")
    return False

def run_logic(action, tools_dir, env_path):
    if action == "search":
        query = request.args.get('q', '').strip()
        sql = "SELECT mf_artist_id, artist_name, biography, photo_path FROM library_artist WHERE artist_name LIKE ?"
        results = db_engine.execute_query(sql, (f"%{query}%",))
        for r in results:
            r['md5_hash'] = get_md5_hash(r['artist_name'])
        return jsonify({"status": "success", "data": results})

    elif action == "get_details":
        mf_id = request.args.get('mf_id')
        sql = "SELECT * FROM library_artist WHERE mf_artist_id = ?"
        results = db_engine.execute_query(sql, (mf_id,))
        if results:
            data = results[0]
            data['md5_hash'] = get_md5_hash(data['artist_name'])
            return jsonify({"status": "success", "data": data})
        return jsonify({"status": "error", "message": "Not found"})

    elif action == "generate_bio":
        data = request.json
        artist_name = data.get('artist_name')
        is_enhanced = data.get('enhanced', False)
        
        prompt = (f"Write a {'deep, comprehensive 5-paragraph' if is_enhanced else 'concise, 3-paragraph'} "
                  f"professional biography for the artist '{artist_name}'. "
                  f"Word count: {'450-500' if is_enhanced else '250-300'} words. "
                  f"Start with the artist name.")
        
        client = genai.Client(api_key=config_handler.GEMINI_API_KEY())
        try:
            response = client.models.generate_content(model="gemini-flash-latest", contents=prompt)
            bio_text = response.text
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

        target_path = get_hashed_path(artist_name)
        fetch_artist_portrait(artist_name, target_path)

        return jsonify({
            "status": "success", 
            "biography": bio_text,
            "md5_hash": get_md5_hash(artist_name)
        })

    elif action == "upload_local_photo":
        data = request.json
        artist_name = data.get('artist_name')
        local_path = data.get('local_path')
        target_path = get_hashed_path(artist_name)
        if process_and_save_image(local_path, target_path, is_local=True):
            return jsonify({"status": "success", "md5_hash": get_md5_hash(artist_name)})
        return jsonify({"status": "error", "message": "Failed to process local image"})

    elif action == "save_bio":
        data = request.json
        sql = "UPDATE library_artist SET biography = ?, photo_path = ?, bio_updated_at = CURRENT_TIMESTAMP WHERE mf_artist_id = ?"
        path = str(get_hashed_path(data.get('artist_name')))
        success = db_engine.execute_query(sql, (data['biography'], path, data['mf_artist_id']), commit=True)
        return jsonify({"status": "success" if success else "error"})

    return jsonify({"status": "error", "message": "Unknown action"})
# --- END OF FILE biography.py ---