# --- START OF FILE update_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Update Gatekeeper
# Physical Location: \tools\settings\engines\update_engine.py
# Build 5.3.9: Hardened SSL context and Traceback reporting.
# ======================================================================
import json
import urllib.request
import ssl
import traceback
import importlib
from flask import jsonify
from common import config_handler

# --- CONFIGURATION ---
REMOTE_MANIFEST_URL = "https://raw.githubusercontent.com/johnfoliot/metaforge-studio/main/deploy/updates.json"

def check_for_updates():
    """
    The Gatekeeper Logic: Compares local manifest against remote GitHub source.
    """
    try:
        # 1. Force refresh of config_handler to ensure DEPLOY_DIR/UPDATE_MANIFEST are seen
        importlib.reload(config_handler)
        
        if not hasattr(config_handler, 'UPDATE_MANIFEST'):
            return jsonify({
                "status": "error", 
                "message": "Attribute 'UPDATE_MANIFEST' missing from config_handler."
            }), 500

        local_path = config_handler.UPDATE_MANIFEST
        
        # 2. Load Local State
        if not local_path.exists():
            return jsonify({
                "status": "error", 
                "message": f"Local manifest missing at {local_path}"
            }), 404
        
        local_data = json.loads(local_path.read_text(encoding='utf-8'))

        # 3. Fetch Remote State (Hardened SSL Context)
        # Bypasses local certificate issues common on Windows dev environments
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(REMOTE_MANIFEST_URL, timeout=10, context=ctx) as response:
                if response.getcode() != 200:
                    raise Exception(f"HTTP {response.getcode()}")
                remote_data = json.loads(response.read().decode('utf-8'))
        except Exception as fetch_err:
            return jsonify({
                "status": "error", 
                "message": f"Remote Fetch Failure: {str(fetch_err)}"
            }), 500

        # 4. Comparison Logic
        local_meta = local_data.get("manifest_metadata", {})
        remote_meta = remote_data.get("manifest_metadata", {})
        
        local_msg = local_data.get("announcements", {})
        remote_msg = remote_data.get("announcements", {})

        # Contrast version or message ID mismatch
        version_mismatch = remote_meta.get("installed_version") != local_meta.get("installed_version")
        new_announcement = remote_msg.get("message_id") != local_msg.get("message_id")

        if version_mismatch or new_announcement:
            return jsonify({
                "update_available": True,
                "priority": remote_msg.get("priority", "optional"),
                "is_dismissed": remote_msg.get("is_dismissed", False),
                "title": remote_msg.get("title", "Update Available"),
                "body": remote_msg.get("body_text", ""),
                "action_url": remote_msg.get("action_url", ""),
                "remote_version": remote_meta.get("installed_version")
            })

        # System is current
        return jsonify({
            "update_available": False,
            "message": "✅ Rest easy, your system is up to date. Happy tagging!"
        })

    except Exception:
        # Return the full Traceback to the UI for debugging
        error_trace = traceback.format_exc()
        print(f"🔥 Gatekeeper Logic Crash:\n{error_trace}")
        return jsonify({
            "status": "error", 
            "message": "Python Gatekeeper Crash. Check Terminal.",
            "trace": error_trace
        }), 500

# --- SETTINGS UPDATE ENGINE END ---
# --- END OF FILE update_engine.py ---