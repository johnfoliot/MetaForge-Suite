# --- START OF FILE update_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Update Engine
# Physical Location: \tools\settings\engines\update_engine.py
# Build 5.3.19: Implemented Heartbeat Timestamping and UI Echo.
# ======================================================================
import json
import urllib.request
import ssl
import traceback
import time
from flask import jsonify, request
from common import config_handler

# --- CONFIGURATION ---
REMOTE_MANIFEST_URL = "https://raw.githubusercontent.com/johnfoliot/MetaForge-Suite/main/deploy/updates.json"

def check_for_updates():
    """
    The Update Logic: Compares manifests and updates the local 'last_checked' heartbeat.
    """
    try:
        if not hasattr(config_handler, 'UPDATE_MANIFEST'):
            return jsonify({"status": "error", "message": "System config mismatch."}), 500

        local_path = config_handler.UPDATE_MANIFEST
        
        # 1. Load Local State
        if not local_path.exists():
            return jsonify({"status": "error", "message": "Local manifest missing."}), 404
        
        raw_local = local_path.read_text(encoding='utf-8-sig').strip()
        local_data = json.loads(raw_local)

        # 2. Fetch Remote State (Cache-Busted)
        cache_buster = f"?v={int(time.time())}"
        target_url = REMOTE_MANIFEST_URL + cache_buster
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(target_url, timeout=10, context=ctx) as response:
            remote_data = json.loads(response.read().decode('utf-8-sig'))

        # 3. Heartbeat Update: Always update the local 'last_checked' timestamp
        current_time_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        current_time_display = time.strftime("%Y-%m-%d", time.gmtime())
        
        local_data["manifest_metadata"]["last_checked"] = current_time_iso
        
        # 4. Extraction & Comparison
        local_meta = local_data.get("manifest_metadata", {})
        remote_meta = remote_data.get("manifest_metadata", {})
        local_msg = local_data.get("announcements", {})
        remote_msg = remote_data.get("announcements", {})

        version_mismatch = remote_meta.get("installed_version") != local_meta.get("installed_version")
        is_new_id = str(remote_msg.get("message_id")) != str(local_msg.get("message_id"))
        was_dismissed = local_msg.get("is_dismissed", False) if not is_new_id else False

        # Physical Write: Commit the heartbeat to the local file immediately
        local_path.write_text(json.dumps(local_data, indent=4), encoding='utf-8')

        if version_mismatch or is_new_id or (not was_dismissed):
            if not version_mismatch and not is_new_id and was_dismissed:
                return jsonify({
                    "update_available": False,
                    "message": "✅ Rest easy, your system is up to date. Happy tagging!",
                    "last_checked": current_time_display
                })

            return jsonify({
                "update_available": True,
                "priority": remote_msg.get("priority", "optional"),
                "message_id": remote_msg.get("message_id"),
                "title": remote_msg.get("title", "Update Available"),
                "body": remote_msg.get("body_text", ""),
                "action_url": remote_msg.get("action_url", ""),
                "remote_version": remote_meta.get("installed_version"),
                "last_checked": current_time_display
            })

        return jsonify({
            "update_available": False,
            "message": "✅ Rest easy, your system is up to date. Happy tagging!",
            "last_checked": current_time_display
        })

    except Exception:
        return jsonify({"status": "error", "trace": traceback.format_exc()}), 500

def commit_update():
    """
    Physically overwrites the local updates.json to synchronize state.
    Triggered when the user clicks 'Accept' or 'Dismiss'.
    """
    try:
        local_path = config_handler.UPDATE_MANIFEST
        payload = request.json 
        
        new_manifest = {
            "manifest_metadata": {
                "schema_version": "1.0.0",
                "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "installed_version": payload.get("remote_version")
            },
            "announcements": {
                "message_id": payload.get("message_id"),
                "priority": payload.get("priority", "optional"),
                "is_dismissed": payload.get("dismissed", False),
                "title": payload.get("title"),
                "body_text": payload.get("body"),
                "action_url": payload.get("action_url")
            }
        }
        
        local_path.write_text(json.dumps(new_manifest, indent=4), encoding='utf-8')
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SETTINGS UPDATE ENGINE END ---
# --- END OF FILE update_engine.py ---