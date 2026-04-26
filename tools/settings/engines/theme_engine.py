# ======================================================================
# MetaForge Mini-Engine: Theme Discovery & Parsing
# Physical Location: \tools\settings\engines\theme_engine.py
# ======================================================================
import re
from pathlib import Path
from flask import jsonify

# --- SETTINGS THEME ENGINE ---

def discover(base_dir):
    """
    Scans /ui/css/ for theme fragments and parses their color variables.
    """
    css_dir = base_dir / "ui" / "css"
    themes = []
    
    # Standard MetaForge variable set to extract for UI previews
    varnames = [
        '--bg-main', '--bg-accent', '--bg-stage', '--mf-gold', 
        '--text-output', '--text-message', '--status-success', 
        '--status-error', '--input-foreground', '--input-background'
    ]
    
    try:
        if css_dir.exists():
            for f in css_dir.glob("*_theme.css"):
                content = f.read_text(encoding='utf-8')
                palette = {}
                
                # Extract hex codes using regex for each standard variable
                for var in varnames:
                    match = re.search(rf'{var}:\s*(#[0-9a-fA-F]+)', content)
                    palette[var] = match.group(1) if match else "#333"

                # Generate a human-readable label
                label = f.name.replace("_theme.css", "").replace("_", " ").title()
                
                themes.append({
                    "file": f.name,
                    "name": label,
                    "palette": palette
                })
        
        # Sort alphabetically by name for UI consistency
        return jsonify(sorted(themes, key=lambda x: x['name']))
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SETTINGS THEME ENGINE END ---