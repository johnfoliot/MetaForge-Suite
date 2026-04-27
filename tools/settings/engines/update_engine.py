# --- START OF FILE update_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Update Gatekeeper
# Physical Location: \tools\settings\engines\update_engine.py
# Build 5.3.11: Corrected Remote GitHub URL for MetaForge-Suite.
# ======================================================================
import json
import urllib.request
import ssl
import traceback
from flask import jsonify
from common import config_handler

# --- CONFIGURATION ---
# Corrected repository name to MetaForge-Suite
REMOTE_MANIFEST_URL = "https://raw.githubusercontent.com/johnfoliot/MetaForge-Suite/main/deploy/updates.json"

def check_for_updates():
    """
    The Gatekeeper Logic: Compares local manifest against remote GitHub source.
    """
    print("\n Initializing Update Check...")
    
    try:
        # 1. Path Verification
        if not hasattr(config_handler, 'UPDATE_MANIFEST'):
            print("  [!] Error: config_handler missing UPDATE_MANIFEST attribute.")
            return jsonify({"status": "error", "message": "System config mismatch."}), 500

        local_path = config_handler.UPDATE_MANIFEST
        print(f"  [>] Target Local Manifest: {local_path}")

        # 2. Load Local State
        if not local_path.exists():
            print(f"  [!] Error: Local file not found at {local_path}")
            return jsonify({"status": "error", "message": "Local manifest missing."}), 404
        
        try:
            raw_local = local_path.read_text(encoding='utf-8-sig').strip()
            local_data = json.loads(raw_local)
            print(f"  [>] Local file read success.")
        except json.JSONDecodeError as je:
            print(f"  [!] JSON Syntax Error in local file: {str(je)}")
            return jsonify({"status": "error", "message": "Local manifest corrupted."}), 500

        # 3. Fetch Remote State
        print(f"  [>] Fetching remote from: {REMOTE_MANIFEST_URL}")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(REMOTE_MANIFEST_URL, timeout=10, context=ctx) as response:
                remote_raw = response.read().decode('utf-8-sig')
                remote_data = json.loads(remote_raw)
                print("  [>] Remote fetch and parse success.")
        except Exception as fetch_err:
            print(f"  [!] Remote fetch failed: {str(fetch_err)}")
            return jsonify({"status": "error", "message": f"Remote fetch failed: {str(fetch_err)}"}), 500

        # 4. Comparison Logic
        local_meta = local_data.get("manifest_metadata", {})
        remote_meta = remote_data.get("manifest_metadata", {})
        local_msg = local_data.get("announcements", {})
        remote_msg = remote_data.get("announcements", {})

        version_mismatch = remote_meta.get("installed_version") != local_meta.get("installed_version")
        new_announcement = remote_msg.get("message_id") != local_msg.get("message_id")

        if version_mismatch or new_announcement:
            print("  [!] Update Detected. Dispatching announcement to UI.")
            return jsonify({
                "update_available": True,
                "priority": remote_msg.get("priority", "optional"),
                "is_dismissed": remote_msg.get("is_dismissed", False),
                "title": remote_msg.get("title", "Update Available"),
                "body": remote_msg.get("body_text", ""),
                "action_url": remote_msg.get("action_url", ""),
                "remote_version": remote_meta.get("installed_version")
            })

        print("  [OK] System is up to date.")
        return jsonify({
            "update_available": False,
            "message": "✅ Rest easy, your system is up to date. Happy tagging!"
        })

    except Exception:
        error_trace = traceback.format_exc()
        print(f"🔥 Critical Crash:\n{error_trace}")
        return jsonify({"status": "error", "trace": error_trace}), 500

# --- SETTINGS UPDATE ENGINE END ---
# --- END OF FILE update_engine.py ---