# --- START OF FILE biography.py ---
# ======================================================================
# MetaForge Tool: Biography Builder Logic
# Build 1.0.42: Discogs Token Fix + Dual Prompt Restoration
# File Location: \tools\biography\biography.py
# ======================================================================
import hashlib
import requests
import os
import time
from io import BytesIO
from PIL import Image, ImageOps
from flask import request, jsonify
from google import genai
from common import config_handler, db_engine

def get_md5_hash(artist_name):
    return hashlib.md5(artist_name.lower().encode('utf-8')).hexdigest()

def get_hashed_path(artist_name):
    photos_dir = config_handler.PROJECT_ROOT / "photos"
    if not photos_dir.exists():
        photos_dir.mkdir(parents=True)
    return photos_dir / f"{get_md5_hash(artist_name)}.jpg"

def run_logic(action, tools_dir, env_path):

    # SEARCH
    if action == "search":
        query = request.args.get('q', '').strip()
        results = db_engine.execute_query(
            "SELECT mf_artist_id, artist_name, biography, photo_path FROM library_artist WHERE artist_name LIKE ?",
            (f"%{query}%",)
        )
        for r in results:
            r['md5_hash'] = get_md5_hash(r['artist_name'])
        return jsonify({"status": "success", "data": results})

    # GENERATE BIO
    elif action == "generate_bio":
        data = request.json
        artist_name = data.get('artist_name')
        mf_id = data.get('mf_artist_id')
        is_enhanced = data.get('enhanced', False)

        # Dual Prompt: Standard vs Enhanced
        if is_enhanced:
            prompt = (
                f"Write a deep, comprehensive 5-paragraph professional biography for the artist '{artist_name}'. "
                f"The total word count MUST be between 450 and 500 words. "
                f"Structure: 1:Origins, 2:Musical style, 3:Career milestones, 4:Challenges and innovations, 5:Legacy. "
                f"Start with the artist name. Be detailed and verbose."
            )
        else:
            prompt = (
                f"Write a concise, 3-paragraph professional biography for the artist '{artist_name}'. "
                f"The total word count MUST be between 250 and 300 words. "
                f"Structure: 1:Origins, 2:Musical style and milestones, 3:Legacy. "
                f"Start with the artist name."
            )

        # AI Bio Generation
        client = genai.Client(api_key=config_handler.GEMINI_API_KEY())
        try:
            bio_text = client.models.generate_content(model="gemini-flash-latest", contents=prompt).text
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

        # Discogs Image Fetch
        target_path = str(get_hashed_path(artist_name))
        token = config_handler.DISCOGS_TOKEN()
        headers = {"User-Agent": "MetaForge/1.0", "Authorization": f"Discogs token={token}"}

        try:
            time.sleep(1.0)
            res = requests.get(
                f"https://api.discogs.com/database/search?q={artist_name}&type=artist",
                headers=headers, timeout=15
            ).json()

            if res.get('results'):
                img_url = res['results'][0].get('cover_image')
                if img_url:
                    img_req = requests.get(img_url, headers=headers, timeout=15)
                    if img_req.status_code == 200:
                        img = Image.open(BytesIO(img_req.content)).convert("RGB")
                        img = ImageOps.pad(img, (500, 500), method=Image.Resampling.LANCZOS, color=(0, 0, 0))
                        img.save(target_path, "JPEG", quality=90)

                        # Atomic DB update once image is confirmed saved
                        db_engine.execute_query(
                            "UPDATE library_artist SET biography = ?, photo_path = ?, bio_updated_at = CURRENT_TIMESTAMP WHERE mf_artist_id = ?",
                            (bio_text, target_path, mf_id), commit=True
                        )
        except Exception as e:
            print(f"[BioBuilder] IO/Fetch Exception: {e}")

        return jsonify({"status": "success", "biography": bio_text, "md5_hash": get_md5_hash(artist_name)})

    # UPLOAD LOCAL PHOTO (manual override)
    elif action == "upload_local_photo":
        data = request.json
        artist_name = data.get('artist_name')
        local_path = data.get('local_path')
        if not artist_name or not local_path:
            return jsonify({"status": "error", "message": "Missing artist_name or local_path"})
        if not os.path.exists(local_path):
            return jsonify({"status": "error", "message": "File not found"})

        target_path = str(get_hashed_path(artist_name))
        try:
            img = Image.open(local_path).convert("RGB")
            img = ImageOps.pad(img, (500, 500), method=Image.Resampling.LANCZOS, color=(0, 0, 0))
            img.save(target_path, "JPEG", quality=90)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Failed to process image: {e}"})

        return jsonify({"status": "success", "md5_hash": get_md5_hash(artist_name)})

    # GET DETAILS
    elif action == "get_details":
        mf_id = request.args.get('mf_id')
        results = db_engine.execute_query(
            "SELECT * FROM library_artist WHERE mf_artist_id = ?", (mf_id,)
        )
        if results:
            data = results[0]
            data['md5_hash'] = get_md5_hash(data['artist_name'])
            return jsonify({"status": "success", "data": data})
        return jsonify({"status": "error", "message": "Not found"})

    # SAVE BIO
    elif action == "save_bio":
        data = request.json
        sql = "UPDATE library_artist SET biography = ?, photo_path = ?, bio_updated_at = CURRENT_TIMESTAMP WHERE mf_artist_id = ?"
        path = str(get_hashed_path(data.get('artist_name')))
        success = db_engine.execute_query(sql, (data['biography'], path, data['mf_artist_id']), commit=True)
        return jsonify({"status": "success" if success else "error"})

    return jsonify({"status": "error", "message": "Unknown action"})

# --- END OF FILE biography.py ---