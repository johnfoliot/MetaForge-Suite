# --- START OF FILE routes.py ---
# ======================================================================
# 🔗 MetaForge Studio: Universal Logic Router
# File Location: \MetaForge Suite\routes.py
# Build 1.8.8: Dynamic Dispatcher + Static Artist Photo Routing
# ======================================================================
import sys
import os
import importlib.util
import traceback
from flask import request, jsonify, Response, stream_with_context, send_from_directory

def initialize_routes(app, window_func, TOOLS_DIR, ENV_PATH, set_file_attribute):
    """
    Wires a single, universal dispatcher to the Flask app.
    This replaces all hardcoded tool routes.
    """

    @app.route('/run_tool_logic/<tool_id>', methods=['GET', 'POST'])
    @app.route('/run_tool_logic/<tool_id>/<action>', methods=['GET', 'POST'])
    def universal_dispatcher(tool_id, action=None):
        """
        The Master Dispatcher: Dynamically loads the Python module for ANY tool.
        URL Pattern: /run_tool_logic/[folder_name]/[optional_sub_action]
        """
        # 1. Construct the path to the tool's python logic
        logic_path = TOOLS_DIR / tool_id / f"{tool_id}.py"

        if not logic_path.exists():
            print(f"DEBUG: Logic script missing at {logic_path}")
            return jsonify({
                "status": "error", 
                "message": f"Module {tool_id}.py not found in tools folder."
            }), 404

        try:
            # 2. Dynamic Module Loading
            spec = importlib.util.spec_from_file_location(tool_id, str(logic_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 3. Execution Phase
            if hasattr(module, 'run_logic'):
                return module.run_logic(action, TOOLS_DIR, ENV_PATH)
            
            # Legacy/Fallback
            elif hasattr(module, 'handle_tool_task'):
                data = request.json if request.is_json else request.args.to_dict()
                return Response(stream_with_context(module.handle_tool_task(data)), mimetype='text/html')
            
            else:
                return jsonify({
                    "status": "error", 
                    "message": f"Function run_logic() not found in {tool_id}.py"
                }), 500

        except Exception:
            error_trace = traceback.format_exc()
            print(f"🔥 MetaForge Dispatcher Error [{tool_id}]:\n{error_trace}")
            return jsonify({
                "status": "error", 
                "message": "Python Execution Error. Check Terminal.",
                "trace": error_trace
            }), 500

    # --- [ FIRST-RUN SETUP (v2 rebuild, 2026-11-17) ] ---
    # Used by ui/html/setup.html only, and only until MetaForge is set up:
    # once the settings file exists both routes refuse (setup can never
    # overwrite real settings). The work is in ui/setup_engine.py.
    import setup_engine

    def _already_set_up():
        return jsonify({"status": "error", "message": "MetaForge is already set up. Change settings in Settings."}), 409

    @app.route('/setup/scan')
    def setup_scan():
        if ENV_PATH.exists():
            return _already_set_up()
        return jsonify(setup_engine.scan(request.args.get('path', '')))

    @app.route('/setup/save', methods=['POST'])
    def setup_save():
        if ENV_PATH.exists():
            return _already_set_up()
        body, code = setup_engine.save(ENV_PATH, ENV_PATH.parent, request.get_json(silent=True) or {})
        if code == 200:
            # The tools read the keys from the environment: load them now,
            # so MetaForge works straight away without a restart.
            from dotenv import load_dotenv
            load_dotenv(ENV_PATH, override=True)
        return jsonify(body), code
# --- END OF FILE routes.py ---