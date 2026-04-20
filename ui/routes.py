# ======================================================================
# 🔗 MetaForge Studio: Logic Router (Include File)
# ======================================================================
import os
import sys
import importlib
import traceback
import json
from flask import request, jsonify, Response, redirect, stream_with_context
from pathlib import Path
from dotenv import load_dotenv

def initialize_routes(app, window_func, TOOLS_DIR, ENV_PATH, set_file_attribute):
    """Wires the dynamic tool logic to the Flask app instance."""

    # --- [ ROUTE: SETTINGS PAGE ] -------------------------------
    @app.route('/run_tool_logic/settings', methods=['GET', 'POST'])
    def settings_route():
        s_path = TOOLS_DIR / "settings"
        if str(s_path) not in sys.path:
            sys.path.append(str(s_path))
        import settings_logic
        importlib.reload(settings_logic)
        if request.method == 'POST':
            data = request.json
            result = settings_logic.update_settings(ENV_PATH, data, set_file_attribute)
            return jsonify(result)
        return jsonify(settings_logic.get_current_settings(ENV_PATH))
        
    # --- [ ROUTE: SETTINGS PAGE END ] -----

    # --- [ ROUTE: GET LOCAL MANIFEST ] -------------------------------
    @app.route('/run_tool_logic/settings/get_local_manifest', methods=['GET'])
    def get_local_manifest_route():
        """Returns the current local manifest data to populate the UI."""
        s_path = TOOLS_DIR / "settings"
        if str(s_path) not in sys.path:
            sys.path.append(str(s_path))
        import settings_logic
        importlib.reload(settings_logic)
        
        # Pulls from D:\MetaForge\audio\data\manifest.json
        return jsonify(settings_logic.get_local_manifest_only())

    # --- [ ROUTE: MANIFEST MASTER SYNC ] -----------------------------
    @app.route('/run_tool_logic/settings/sync_manifest', methods=['POST'])
    def sync_manifest_route():
        """Single handshake comparing local manifest vs Google Drive Master."""
        s_path = TOOLS_DIR / "settings"
        if str(s_path) not in sys.path:
            sys.path.append(str(s_path))
        import settings_logic
        importlib.reload(settings_logic)
        
        # The single 'Interview' between the two JSON files
        result = settings_logic.sync_manifest_status()
        
        return jsonify(result)
    # --- [ ROUTE: MANIFEST MASTER SYNC END ] -------------------------
     
    # --- [ ROUTE: INSTALL UPDATE ] -----------------------------------
    @app.route('/run_tool_logic/settings/install_update', methods=['POST'])
    def install_update_route():
        """Triggers the ZIP download and local file mirroring engine."""
        s_path = TOOLS_DIR / "settings"
        if str(s_path) not in sys.path:
            sys.path.append(str(s_path))
        import settings_logic
        importlib.reload(settings_logic)
        
        # Calls the update engine in settings_logic.py
        result = settings_logic.perform_update_from_manifest()
        
        return jsonify(result)
    # --- [ ROUTE: INSTALL UPDATE END ] -------------------------------

    # --- [ ROUTE: ACOUSTID TOOL ] ------------------------------------
    @app.route('/run_tool_logic/acoustid')
    def acoustid_logic_route():
        task_type = request.args.get('task')
        t_path = TOOLS_DIR / "acoustid"
        if str(t_path) not in sys.path:
            sys.path.append(str(t_path))
        
        try:
            import acoustid_logic
            importlib.reload(acoustid_logic)
            
            # Direct connection to the generator functions in acoustid_logic.py
            if task_type == 'submit':
                return Response(stream_with_context(acoustid_logic.submit_fingerprints_stream()), mimetype='text/html')
            elif task_type == 'resolve':
                return Response(stream_with_context(acoustid_logic.resolve_ids_stream()), mimetype='text/html')
            
            return jsonify({"status": "error", "message": "Unknown task"})
        except Exception as e:
            # Logs to the local Python terminal only; sends a clean error to the UI console
            print(f"AcoustID Route Error: {str(e)}")
            return Response("<div>Error initializing task. Check terminal.</div>", mimetype='text/html')
    
    # --- [ ROUTE: ACOUSTID TOOL END ] --------------------------------

    # --- [ ROUTE: UNPACKER/CONVERTER TOOL ] ------------------------------------------
    @app.route('/run_tool_logic/unpack')
    def unpack_logic_route():
        target_path = request.args.get('path')
        try:
            t_path = TOOLS_DIR / "unpack"
            if str(t_path) not in sys.path: 
                sys.path.append(str(t_path))
            import unpacker_logic
            importlib.reload(unpacker_logic)
            return Response(stream_with_context(unpacker_logic.run_unpack(target_path)), mimetype='text/html')
        except Exception as e:
            return f"<span style='color:red;'>Logic Error: {str(e)}</span>"
 
    # --- [ ROUTE: UNPACKER/CONVERTER TOOL END ] -------------
    
    # --- [ ROUTE: YOUTUBE TO MP3 ] ------------------------------------
    @app.route('/run_tool_logic/youtube', methods=['POST'])
    def youtube_route():
        """Standardized route for YouTube downloads."""
        try:
            # Ensure the youtube folder is in the path
            y_path = TOOLS_DIR / "youtube"
            if str(y_path) not in sys.path:
                sys.path.append(str(y_path))
            
            import youtube_logic
            importlib.reload(youtube_logic)
            
            data = request.json
            # Note: task "convert" is passed to your [DISPATCHER]
            return Response(
                stream_with_context(youtube_logic.handle_youtube_task("convert", data)), 
                mimetype='text/html'
            )
            
        except Exception as e:
            error_trace = traceback.format_exc()
            def error_generator():
                yield f"<div style='color:#ff0000; font-weight:bold;'>🔥 ROUTING ERROR:</div>"
                yield f"<pre style='color:#ff4444; background:#1a1a1a; padding:15px; border:1px solid #444;'>{error_trace}</pre>"
            return Response(stream_with_context(error_generator()), mimetype='text/html')
    # --- [ ROUTE: YOUTUBE TO MP3 END ] ---
    
    # --- [ ROUTE: AUDIO REPAIR ] --------------------------------------
    @app.route('/route_audio_repair', methods=['POST'])
    def route_audio_repair():
        import importlib.util
        import traceback
        from flask import request, Response, stream_with_context
        
        # FIXED: Directory name is 'repair' based on verified path
        logic_path = TOOLS_DIR / "repair" / "repair_logic.py"
        
        try:
            # DYNAMIC LOADER: Bypasses sys.path issues and module name collisions
            spec = importlib.util.spec_from_file_location("repair_logic", str(logic_path))
            repair_logic = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(repair_logic)
            
            data = request.json
            return Response(stream_with_context(repair_logic.handle_tool_task(data)), mimetype='text/html')
            
        except Exception as e:
            error_trace = traceback.format_exc()
            def error_generator():
                yield f"<div style='color:#ff0000; font-weight:bold;'>🔥 PYTHON EXECUTION ERROR:</div>"
                yield f"<pre style='color:#ff4444; background:#1a1a1a; padding:15px; border:1px solid #444; overflow:auto;'>{error_trace}</pre>"
            return Response(stream_with_context(error_generator()), mimetype='text/html')
    # --- AUDIO REPAIR ROUTE END ---
    
    # --- [ ROUTE: MUSICBRAINZ ] ---
    @app.route('/run_tool_logic/musicbrainz', methods=['POST', 'GET'])
    def musicbrainz_route():
        try:
            # Standardized Path Injection 
            t_path = TOOLS_DIR / "musicbrainz"
            if str(t_path) not in sys.path:
                sys.path.append(str(t_path))

            import musicbrainz_logic
            importlib.reload(musicbrainz_logic)

            data = request.json if request.is_json else None
            return Response(
                stream_with_context(musicbrainz_logic.handle_musicbrainz_task("start", data)),
                mimetype='text/html'
            )
        except Exception:
            # Stream traceback to UI console 
            return Response(f"<pre>{traceback.format_exc()}</pre>", mimetype='text/html')
    # --- [ END MUSICBRAINZ ROUTE ] ---
    
    # --- [ ROUTE: INITIAL SETUP ] -------------------------------------
    @app.route('/save_setup', methods=['POST'])
    def save_setup():
        try:
            email = request.form.get('user_email')
            acc = request.form.get('acoustid_key')
            gem = request.form.get('gemini_key')
            lib = request.form.get('library_root')
            content = f"USER_EMAIL={email}\\nACOUSTID_KEY={acc}\\nGEMINI_KEY={gem}\\nLIBRARY_ROOT={lib}\\n"
            if ENV_PATH.exists(): 
                set_file_attribute(ENV_PATH, 128)
            ENV_PATH.write_text(content)
            set_file_attribute(ENV_PATH, 2)
            load_dotenv(ENV_PATH, override=True)
            return redirect('/')
        except Exception as e: 
            return f"Error: {str(e)}", 500
            
        # --- [ ROUTE: INITIAL SETUP END ] -------------