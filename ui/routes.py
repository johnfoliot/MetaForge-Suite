# ======================================================================
# 🔗 MetaForge Studio: Universal Logic Router
# File Location: \MetaForge Suite\ui\routes.py
# ======================================================================
import sys
import importlib.util
import traceback
from flask import request, jsonify, Response, stream_with_context

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
        # Example: /tools/settings/settings.py
        logic_path = TOOLS_DIR / tool_id / f"{tool_id}.py"

        if not logic_path.exists():
            print(f"DEBUG: Logic script missing at {logic_path}")
            return jsonify({
                "status": "error", 
                "message": f"Module {tool_id}.py not found in tools folder."
            }), 404

        try:
            # 2. Dynamic Module Loading (Bypasses sys.path collisions)
            spec = importlib.util.spec_from_file_location(tool_id, str(logic_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 3. Execution Phase
            # Every MetaForge tool must have a run_logic(action, tools_dir, env_path) function
            if hasattr(module, 'run_logic'):
                return module.run_logic(action, TOOLS_DIR, ENV_PATH)
            
            # Legacy/Fallback: If the tool uses the old 'handle_task' style
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

    # --- [ SPECIAL ROUTE: SETUP RE-ENTRY ] ---
    @app.route('/save_setup', methods=['POST'])
    def save_setup():
        """Handles the initial bootstrap config write."""
        try:
            data = request.form
            content = (
                f"USER_EMAIL={data.get('user_email')}\n"
                f"ACOUSTID_KEY={data.get('acoustid_key')}\n"
                f"GEMINI_KEY={data.get('gemini_key')}\n"
                f"LIBRARY_ROOT={data.get('library_root')}\n"
                f"ENABLED_TOOLS=dashboard:0,settings:99\n"
            )
            ENV_PATH.write_text(content)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500